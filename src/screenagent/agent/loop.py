"""Perceive-think-act loop using Claude API."""

from __future__ import annotations

import asyncio
import base64
import logging
import subprocess
import time

import anthropic

from screenagent.types import ScreenState, ToolResult
from screenagent.config import Config
from screenagent.perception.composite import CompositePerceiver
from screenagent.action.cgevent import CGEventActor
from screenagent.action.cdp import CDPActor
from screenagent.agent.tools import TOOLS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a GUI automation agent running on macOS. You can see the screen and interact with any application using mouse clicks, keyboard input, and browser navigation.

Strategy:
1. If the task involves searching on a website, use open_url with the search URL directly. Examples:
   - Google search: open_url("https://www.google.com/search?q=YOUR_QUERY")
   - YouTube search: open_url("https://www.youtube.com/results?search_query=YOUR_QUERY")
   - Any site: open_url("https://SITE.com") then use browser_eval to fill the search form.
2. If the task mentions navigating to a website, use open_url FIRST.
3. Use browser_eval for precise page interactions (filling inputs, clicking buttons, reading text). It is more reliable than click+type for browser tasks.
4. Fall back to click/type_text/key_press only when browser_eval is unavailable or for non-browser apps.
5. After navigating or completing the action, check the screenshot. If the expected page/result is visible, call done immediately. Do NOT click on random elements after the task is already accomplished.

Guidelines:
- IMPORTANT: For click coordinates, pass x and y as separate numeric values. Correct: {"x": 640, "y": 197}. WRONG: {"x": "640, 197", "y": 197}.
- Use open_url to navigate to a URL — it always works.
- Use browser_eval to interact with page elements directly, e.g.: browser_eval("document.querySelector('textarea').value = 'query'; document.querySelector('form').submit()")
- If the same action fails twice, try a completely different approach.
- If content is not visible on screen, use scroll to find it.
- Call done as soon as the task objective is achieved. For search tasks, seeing the search results page means the task is done.
"""

# Max conversation turns to keep (excluding system + initial instruction)
MAX_HISTORY = 10


class AgentLoop:
    def __init__(self, config: Config | None = None):
        self._config = config or Config.from_env()
        self._client = anthropic.Anthropic(api_key=self._config.anthropic_api_key)
        self._perceiver = CompositePerceiver(cdp_port=self._config.cdp_port)
        self._actor = CGEventActor()
        self._cdp_actor: CDPActor | None = None
        self._cdp_actor_checked = False

    async def _get_cdp_actor(self) -> CDPActor | None:
        if self._cdp_actor is None and not self._cdp_actor_checked:
            self._cdp_actor_checked = True
            if await self._perceiver._ensure_cdp():
                self._cdp_actor = CDPActor(self._perceiver.cdp)
        return self._cdp_actor

    def _build_perception_content(self, state: ScreenState) -> list[dict]:
        """Build Claude message content blocks from ScreenState."""
        content: list[dict] = []

        text = state.to_text()
        if text:
            content.append({"type": "text", "text": text})

        if state.screenshot_png:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(state.screenshot_png).decode(),
                },
            })

        if not content:
            content.append({"type": "text", "text": "No perception data available."})

        return content

    @staticmethod
    def _parse_coord(val) -> float:
        """Parse a coordinate value, handling cases where model sends 'x, y' as a single string."""
        if isinstance(val, (int, float)):
            return float(val)
        import re
        s = str(val).strip()
        # Extract the first number (int or float) from the string
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if m:
            return float(m.group())
        return float(s)

    async def _open_url_via_keyboard(self, url: str, app_name: str = "Google Chrome") -> ToolResult:
        """Navigate browser to a URL using keyboard shortcuts (Cmd+L → Cmd+A → type → Enter)."""
        # Ensure browser is in foreground before sending keyboard events
        self._activate_app(app_name)
        # Focus address bar
        self._actor.key_press("l", ["command"])
        await asyncio.sleep(0.3)
        # Select all existing text
        self._actor.key_press("a", ["command"])
        await asyncio.sleep(0.1)
        # Type the URL
        self._actor.type_text(url)
        await asyncio.sleep(0.3)
        # Press Enter to navigate
        self._actor.key_press("return", None)
        await asyncio.sleep(2)  # Wait for page load
        # Reconnect CDP since page navigation invalidates the old websocket
        try:
            await self._perceiver.cdp._reconnect()
            self._perceiver._cdp_connected = True
        except Exception as exc:
            logger.debug("CDP reconnect after open_url failed: %s", exc)
            self._perceiver._cdp_connected = False
        png = self._perceiver.screenshot()
        return ToolResult(output=f"Navigated to {url} (via keyboard)", screenshot_png=png)

    async def _dispatch_tool(self, name: str, args: dict, app_name: str = "Google Chrome") -> ToolResult:
        """Execute a tool and return the result."""
        # Ensure target app is in foreground for GUI-interactive tools
        if name in ("click", "type_text", "key_press", "scroll", "open_url"):
            self._activate_app(app_name)

        if name == "screenshot":
            png = self._perceiver.screenshot()
            return ToolResult(output="Screenshot captured.", screenshot_png=png)

        elif name == "get_ui_tree":
            tree = self._perceiver._ax.get_ui_tree(args["app_name"])
            if tree:
                return ToolResult(output=tree.to_text())
            return ToolResult(error=f"Could not get UI tree for {args['app_name']}")

        elif name == "click":
            x, y = self._parse_coord(args["x"]), self._parse_coord(args["y"])
            self._actor.click(x, y)
            await asyncio.sleep(0.3)
            png = self._perceiver.screenshot()
            return ToolResult(output=f"Clicked at ({x}, {y})", screenshot_png=png)

        elif name == "type_text":
            self._actor.type_text(str(args["text"]))
            await asyncio.sleep(0.3)
            png = self._perceiver.screenshot()
            return ToolResult(output=f"Typed: {args['text']!r}", screenshot_png=png)

        elif name == "key_press":
            self._actor.key_press(str(args["key"]), args.get("modifiers"))
            await asyncio.sleep(0.3)
            png = self._perceiver.screenshot()
            return ToolResult(output=f"Pressed: {args['key']}", screenshot_png=png)

        elif name == "scroll":
            self._actor.scroll(
                self._parse_coord(args["x"]), self._parse_coord(args["y"]),
                self._parse_coord(args["dx"]), self._parse_coord(args["dy"]),
            )
            await asyncio.sleep(0.3)
            png = self._perceiver.screenshot()
            return ToolResult(output="Scrolled.", screenshot_png=png)

        elif name == "open_url":
            url = str(args["url"])
            # Try CDP navigate first (faster and more reliable), fall back to keyboard
            cdp_actor = await self._get_cdp_actor()
            if cdp_actor is not None:
                try:
                    await cdp_actor.navigate(url)
                    await asyncio.sleep(2)
                    # Reconnect CDP to the new page
                    try:
                        await self._perceiver.cdp._reconnect()
                        self._perceiver._cdp_connected = True
                    except Exception:
                        self._perceiver._cdp_connected = False
                    png = self._perceiver.screenshot()
                    return ToolResult(output=f"Navigated to {url}", screenshot_png=png)
                except Exception as exc:
                    logger.info("CDP navigate failed for open_url (%s), falling back to keyboard", exc)
            return await self._open_url_via_keyboard(url, app_name)

        elif name == "navigate":
            cdp_actor = await self._get_cdp_actor()
            if cdp_actor is None:
                logger.info("CDP unavailable, falling back to open_url for navigation")
                return await self._open_url_via_keyboard(str(args["url"]))
            try:
                await cdp_actor.navigate(args["url"])
            except Exception as exc:
                logger.warning("CDP navigate failed (%s), falling back to open_url", exc)
                return await self._open_url_via_keyboard(str(args["url"]))
            await asyncio.sleep(1)
            png = self._perceiver.screenshot()
            return ToolResult(output=f"Navigated to {args['url']}", screenshot_png=png)

        elif name == "browser_eval":
            cdp_actor = await self._get_cdp_actor()
            if cdp_actor is None:
                return ToolResult(error="CDP not available. Chrome must be running with --remote-debugging-port.")
            try:
                result_str = await self._perceiver.cdp.evaluate_js(str(args["expression"]))
            except Exception as exc:
                # JS may have triggered navigation (form submit, link click) which closes WebSocket.
                # Wait for page load and reconnect, then capture screenshot.
                logger.info("browser_eval caused navigation or error: %s — reconnecting", exc)
                try:
                    await self._perceiver.cdp._reconnect()
                except Exception:
                    pass
                await asyncio.sleep(1)
                png = self._perceiver.screenshot()
                return ToolResult(output="JS executed (page may have navigated).", screenshot_png=png)
            await asyncio.sleep(0.5)
            png = self._perceiver.screenshot()
            return ToolResult(output=f"Result: {result_str}", screenshot_png=png)

        elif name == "done":
            return ToolResult(output=args["summary"], done=True)

        else:
            return ToolResult(error=f"Unknown tool: {name}")

    def _tool_result_to_content(self, result: ToolResult) -> list[dict]:
        """Convert ToolResult to Claude message content blocks."""
        content: list[dict] = []
        if result.error:
            content.append({"type": "text", "text": f"Error: {result.error}"})
        if result.output:
            content.append({"type": "text", "text": result.output})
        if result.screenshot_png:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(result.screenshot_png).decode(),
                },
            })
        return content or [{"type": "text", "text": "OK"}]

    def _trim_messages(self, messages: list[dict], instruction: str) -> list[dict]:
        """Keep the first message (instruction + perception) and last MAX_HISTORY messages."""
        if len(messages) <= MAX_HISTORY + 1:
            return messages
        return [messages[0]] + messages[-(MAX_HISTORY):]

    def run(self, instruction: str, app_name: str = "Google Chrome") -> str:
        """Run the agent loop synchronously. Returns the final summary."""
        return asyncio.run(self.arun(instruction, app_name))

    @staticmethod
    def _activate_app(app_name: str) -> None:
        """Bring the target application to the foreground using osascript."""
        try:
            subprocess.Popen(
                ["osascript", "-e", f'tell application "{app_name}" to activate'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
        except Exception as exc:
            logger.warning("Could not activate app %s: %s", app_name, exc)

    async def arun(self, instruction: str, app_name: str = "Google Chrome") -> str:
        """Run the agent loop asynchronously. Returns the final summary."""
        logger.info("Starting agent with instruction: %s", instruction)

        # Bring target app to foreground
        self._activate_app(app_name)

        # Initial perception
        state = await self._perceiver._perceive_async(app_name, include_screenshot=True)
        initial_content = self._build_perception_content(state)
        initial_content.insert(0, {
            "type": "text",
            "text": f"Task: {instruction}\n\nCurrent screen state:",
        })

        messages: list[dict] = [{"role": "user", "content": initial_content}]

        for step in range(self._config.max_steps):
            logger.info("Step %d/%d", step + 1, self._config.max_steps)

            trimmed = self._trim_messages(messages, instruction)

            response = self._client.messages.create(
                model=self._config.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=trimmed,
            )

            # Process response
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                # Model finished without tool use
                text_parts = [b.text for b in assistant_content if hasattr(b, "text")]
                return "\n".join(text_parts) if text_parts else "Agent finished."

            # Process tool uses
            tool_results: list[dict] = []
            done_summary = None

            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                logger.info("Tool call: %s(%s)", block.name, block.input)
                try:
                    result = await self._dispatch_tool(block.name, block.input, app_name)
                except Exception as exc:
                    logger.warning("Tool %s failed: %s", block.name, exc)
                    result = ToolResult(error=str(exc))

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": self._tool_result_to_content(result),
                })

                if result.done:
                    done_summary = result.output

            messages.append({"role": "user", "content": tool_results})

            if done_summary:
                return done_summary

        return "Agent reached maximum steps without completing the task."

"""Perceive-think-act loop using Claude API."""

from __future__ import annotations

import asyncio
import base64
import logging
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

Guidelines:
- Analyze the screenshot and UI tree to understand the current state before acting.
- Click on specific coordinates visible in the screenshot.
- Use navigate or open_url for browser URLs; use click + type_text for form inputs.
- open_url works without Chrome DevTools Protocol — use it if navigate fails.
- After typing in a search box, press Enter (key_press with key="return") to submit.
- Call the done tool when the task is complete.
- If something doesn't work, try an alternative approach.
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

    async def _get_cdp_actor(self) -> CDPActor | None:
        if self._cdp_actor is None:
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
        s = str(val).strip()
        # If model sent "338, 58" as x, take the first number
        if "," in s:
            s = s.split(",")[0].strip()
        return float(s)

    async def _open_url_via_keyboard(self, url: str) -> ToolResult:
        """Navigate browser to a URL using keyboard shortcuts (Cmd+L → Cmd+A → type → Enter)."""
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
        png = self._perceiver.screenshot()
        return ToolResult(output=f"Navigated to {url} (via keyboard)", screenshot_png=png)

    async def _dispatch_tool(self, name: str, args: dict) -> ToolResult:
        """Execute a tool and return the result."""
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
            return await self._open_url_via_keyboard(url)

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

    async def arun(self, instruction: str, app_name: str = "Google Chrome") -> str:
        """Run the agent loop asynchronously. Returns the final summary."""
        logger.info("Starting agent with instruction: %s", instruction)

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
                result = await self._dispatch_tool(block.name, block.input)

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

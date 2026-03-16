"""Computer Use agent loop — uses Claude's native computer_20251124 tool."""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import subprocess
import time

import anthropic

from screenagent.types import ToolResult
from screenagent.config import Config
from screenagent.perception.screenshot import ScreenshotPerceiver
from screenagent.action.cgevent import CGEventActor

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a computer use agent running on macOS. You control the screen via mouse clicks, keyboard input, and screenshots.

Strategy:
- For browser tasks: use the address bar (Cmd+L) to navigate, then interact with the page.
- For search tasks: navigate directly to search URL (e.g. https://www.google.com/search?q=QUERY).
- Take a screenshot first to understand the current state.
- After completing the task, report what you accomplished.
"""

# Computer use image constraints
MAX_LONG_EDGE = 1568
MAX_PIXELS = 1_150_000


def _get_screen_size() -> tuple[int, int]:
    """Get the main display resolution."""
    try:
        from Quartz import CGDisplayBounds, CGMainDisplayID
        bounds = CGDisplayBounds(CGMainDisplayID())
        return int(bounds.size.width), int(bounds.size.height)
    except Exception:
        return 1440, 900  # fallback


def _compute_scaled_size(width: int, height: int) -> tuple[int, int]:
    """Compute the scaled display size for computer use API."""
    scale = min(
        1.0,
        MAX_LONG_EDGE / max(width, height),
        math.sqrt(MAX_PIXELS / (width * height)),
    )
    return int(width * scale), int(height * scale)


class ComputerUseLoop:
    """Agent loop using Claude's computer_20251124 tool type."""

    def __init__(self, config: Config | None = None):
        self._config = config or Config.from_env()
        self._client = anthropic.Anthropic(api_key=self._config.anthropic_api_key)
        self._screenshot = ScreenshotPerceiver()
        self._actor = CGEventActor()

        # Screen dimensions
        self._screen_w, self._screen_h = _get_screen_size()
        self._scaled_w, self._scaled_h = _compute_scaled_size(self._screen_w, self._screen_h)
        self._scale = self._scaled_w / self._screen_w

        logger.info(
            "Screen: %dx%d → scaled: %dx%d (scale=%.3f)",
            self._screen_w, self._screen_h,
            self._scaled_w, self._scaled_h, self._scale,
        )

    def _to_screen_coords(self, x: int, y: int) -> tuple[float, float]:
        """Convert model coordinates (scaled) back to screen coordinates."""
        return x / self._scale, y / self._scale

    def _take_screenshot_b64(self) -> str:
        """Capture screenshot, resize to scaled dimensions, return base64."""
        png_bytes = self._screenshot.screenshot()
        # Resize to scaled dimensions using sips
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            Path(tmp_path).write_bytes(png_bytes)
            subprocess.run(
                ["sips", "--resampleWidth", str(self._scaled_w), tmp_path],
                capture_output=True, timeout=10,
            )
            resized = Path(tmp_path).read_bytes()
            return base64.b64encode(resized).decode()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _dispatch_action(self, action: str, params: dict) -> str | None:
        """Execute a computer use action. Returns error string or None."""
        if action == "screenshot":
            return None  # Screenshot is handled separately in the loop

        elif action == "left_click":
            coord = params.get("coordinate", [0, 0])
            sx, sy = self._to_screen_coords(coord[0], coord[1])
            self._actor.click(sx, sy)
            time.sleep(0.3)

        elif action == "right_click":
            coord = params.get("coordinate", [0, 0])
            sx, sy = self._to_screen_coords(coord[0], coord[1])
            # CGEvent right click
            from Quartz import (
                CGEventCreateMouseEvent, CGEventPost, CGPointMake,
                kCGEventRightMouseDown, kCGEventRightMouseUp, kCGHIDEventTap,
            )
            point = CGPointMake(sx, sy)
            down = CGEventCreateMouseEvent(None, kCGEventRightMouseDown, point, 0)
            up = CGEventCreateMouseEvent(None, kCGEventRightMouseUp, point, 0)
            CGEventPost(kCGHIDEventTap, down)
            time.sleep(0.05)
            CGEventPost(kCGHIDEventTap, up)
            time.sleep(0.3)

        elif action == "double_click":
            coord = params.get("coordinate", [0, 0])
            sx, sy = self._to_screen_coords(coord[0], coord[1])
            self._actor.double_click(sx, sy)
            time.sleep(0.3)

        elif action == "type":
            text = params.get("text", "")
            self._actor.type_text(text)
            time.sleep(0.1)

        elif action == "key":
            key_combo = params.get("text", "")
            self._execute_key(key_combo)
            time.sleep(0.2)

        elif action == "mouse_move":
            coord = params.get("coordinate", [0, 0])
            sx, sy = self._to_screen_coords(coord[0], coord[1])
            from Quartz import (
                CGEventCreateMouseEvent, CGEventPost, CGPointMake,
                kCGEventMouseMoved, kCGHIDEventTap,
            )
            point = CGPointMake(sx, sy)
            move = CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, 0)
            CGEventPost(kCGHIDEventTap, move)

        elif action == "scroll":
            coord = params.get("coordinate", [0, 0])
            sx, sy = self._to_screen_coords(coord[0], coord[1])
            direction = params.get("scroll_direction", "down")
            amount = params.get("scroll_amount", 3)
            dy = -amount * 50 if direction == "down" else amount * 50
            dx = -amount * 50 if direction == "right" else amount * 50 if direction == "left" else 0
            if direction in ("up", "down"):
                dx = 0
            else:
                dy = 0
            self._actor.scroll(sx, sy, dx, dy)
            time.sleep(0.3)

        elif action == "wait":
            duration = params.get("duration", 1)
            time.sleep(min(duration, 5))

        elif action == "triple_click":
            coord = params.get("coordinate", [0, 0])
            sx, sy = self._to_screen_coords(coord[0], coord[1])
            from Quartz import (
                CGEventCreateMouseEvent, CGEventPost, CGPointMake,
                CGEventSetIntegerValueField, kCGMouseEventClickState,
                kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGHIDEventTap,
            )
            point = CGPointMake(sx, sy)
            for click_count in (1, 2, 3):
                down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
                up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
                CGEventSetIntegerValueField(down, kCGMouseEventClickState, click_count)
                CGEventSetIntegerValueField(up, kCGMouseEventClickState, click_count)
                CGEventPost(kCGHIDEventTap, down)
                time.sleep(0.05)
                CGEventPost(kCGHIDEventTap, up)
                if click_count < 3:
                    time.sleep(0.05)
            time.sleep(0.3)

        else:
            return f"Unknown action: {action}"

        return None

    def _execute_key(self, key_combo: str) -> None:
        """Execute a key combination like 'ctrl+s', 'Return', 'cmd+a'."""
        # Map computer-use key names to CGEvent names
        key_map = {
            "return": "return", "enter": "return",
            "tab": "tab", "space": "space",
            "backspace": "delete", "delete": "delete",
            "escape": "escape", "esc": "escape",
            "up": "up", "down": "down", "left": "left", "right": "right",
            "cmd": "command", "ctrl": "control",
            "alt": "option", "shift": "shift",
            "super": "command", "meta": "command",
        }

        parts = [p.strip().lower() for p in key_combo.split("+")]
        modifiers = []
        key = None

        for part in parts:
            mapped = key_map.get(part, part)
            if mapped in ("command", "shift", "option", "control"):
                modifiers.append(mapped)
            else:
                key = mapped

        if key:
            self._actor.key_press(key, modifiers if modifiers else None)

    @staticmethod
    def _activate_app(app_name: str) -> None:
        """Bring the target application to the foreground."""
        try:
            subprocess.Popen(
                ["osascript", "-e", f'tell application "{app_name}" to activate'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
        except Exception as exc:
            logger.warning("Could not activate app %s: %s", app_name, exc)

    def run(self, instruction: str, app_name: str = "Google Chrome") -> str:
        """Run synchronously."""
        return asyncio.run(self.arun(instruction, app_name))

    async def arun(self, instruction: str, app_name: str = "Google Chrome") -> str:
        """Run the computer use agent loop."""
        logger.info("Starting computer-use agent: %s", instruction)

        self._activate_app(app_name)
        await asyncio.sleep(0.5)

        # Take initial screenshot
        screenshot_b64 = self._take_screenshot_b64()

        messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                ],
            }
        ]

        tools = [
            {
                "type": "computer_20251124",
                "name": "computer",
                "display_width_px": self._scaled_w,
                "display_height_px": self._scaled_h,
                "display_number": 1,
            },
        ]

        for step in range(self._config.max_steps):
            logger.info("Step %d/%d", step + 1, self._config.max_steps)

            # Trim history to avoid context overflow
            trimmed = messages
            if len(messages) > 20:
                trimmed = [messages[0]] + messages[-18:]

            response = self._client.beta.messages.create(
                model=self._config.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=trimmed,
                betas=["computer-use-2025-11-24"],
            )

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # If model finished without tool use
            if response.stop_reason == "end_turn":
                text_parts = [b.text for b in assistant_content if hasattr(b, "text")]
                return "\n".join(text_parts) if text_parts else "Agent finished."

            # Process tool uses
            tool_results: list[dict] = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                action = block.input.get("action", "")
                logger.info("Action: %s %s", action, {k: v for k, v in block.input.items() if k != "action"})

                # Activate app before GUI actions
                if action not in ("screenshot", "wait"):
                    self._activate_app(app_name)

                error = self._dispatch_action(action, block.input)

                if error:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": error,
                        "is_error": True,
                    })
                elif action == "screenshot":
                    # Return screenshot as image
                    screenshot_b64 = self._take_screenshot_b64()
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_b64,
                                },
                            },
                        ],
                    })
                else:
                    # For non-screenshot actions, take a screenshot and return it
                    screenshot_b64 = self._take_screenshot_b64()
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_b64,
                                },
                            },
                        ],
                    })

            messages.append({"role": "user", "content": tool_results})

        return "Agent reached maximum steps without completing the task."

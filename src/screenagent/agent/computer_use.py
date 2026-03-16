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
from screenagent.perception.ax import AXPerceiver
from screenagent.action.cgevent import CGEventActor

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a computer-use agent on macOS. You control the screen via the `computer` tool.

## CRITICAL RULES
- ALWAYS use keyboard shortcuts instead of clicking when possible.
- NEVER click on Spotlight results — type the name and press Return.
- NEVER click the same area more than twice. If it didn't work, try something else.
- When "UI Elements:" text is provided, use it to find exact coordinates of buttons/fields.
- After EVERY action, check 'Current App:' and 'Window Title:' in the tool result to verify you are in the correct application.
- If the app changed unexpectedly (see NOTE messages), use Cmd+Tab or Cmd+Space to switch back IMMEDIATELY.
- If a 'No visible change' note appears, your action likely failed — try a different approach.

## Before EVERY action, state:
1. OBSERVE: What is currently on screen? What does 'Current App:' say?
2. RECALL: What have I already tried? Did it work?
3. PLAN: What will I do next and why?

## How to Open Apps (FOLLOW EXACTLY)
1. Press Cmd+Space (opens Spotlight)
2. Type the app name (e.g. "Calculator")
3. Press Return — this opens the top result. DO NOT click.
4. Wait 1-2 seconds for the app to launch.

## How to Use Calculator (CRITICAL)
- FIRST press Cmd+A then Delete to clear any existing value.
- THEN type the ENTIRE expression in ONE action (e.g. type "number+number", not digit by digit).
- Then press Return to compute the result.
- NEVER click calculator buttons — keyboard is faster and more reliable.
- NEVER type one digit at a time. Combine everything into one type action.

## How to Use Browser
1. FIRST check 'Current App:' to confirm you are in the browser.
2. Cmd+L to focus address bar
3. Press Cmd+A to select all existing text, then type URL, press Return.
4. For search: go to https://www.google.com/search?q=QUERY
5. If the address bar shows an unexpected URL, press Cmd+L, Cmd+A, then type the correct URL.

## Multi-Window Recovery
- If you end up in the wrong app (Finder, Terminal, etc.), press Cmd+Tab to return to the target app.
- NEVER continue actions without verifying you are in the correct app via 'Current App:' in tool results.
- If Cmd+Tab doesn't work, use Cmd+Space to search for and reopen the target app.

## Recovery Rules
- If an action produced no visible change, DO NOT repeat it.
- If the same approach failed twice, try a COMPLETELY different method.
- If you can't find a UI element, use keyboard navigation (Tab, arrow keys).
- If stuck for 3+ steps, take a fresh screenshot and reassess.

## macOS Shortcuts
- Cmd+Space: Spotlight search (open any app)
- Cmd+Tab: Switch between apps
- Cmd+L: Browser address bar
- Cmd+A: Select all (useful to clear fields before typing)
- Cmd+W: Close window/tab
- Cmd+Q: Quit app

## Completion
- When the task is done, describe what you accomplished and stop.
- If you cannot complete the task after trying multiple approaches, explain what went wrong.
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
        self._ax = AXPerceiver()
        self._actor = CGEventActor()
        self._action_log: list[str] = []  # human-readable action descriptions
        self._action_keys: list[str] = []  # compact keys for repetition detection
        self._last_action: str = ""  # track previous action type for context
        self._prev_app: str | None = None
        self._prev_window: str | None = None
        self._target_app_pid: int | None = None  # PID of app launched via Spotlight
        self._host_pid: int | None = self._get_frontmost_pid()  # PID of host (IDE/terminal)
        self._thinking_supported: bool = True  # will auto-disable on first failure
        self._spotlight_active: bool = False
        self._spotlight_typed: str = ""
        self._target_app_name: str | None = None

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
            if self._spotlight_active:
                self._spotlight_typed = text  # last type is the app name
            self._actor.type_text(text)
            time.sleep(0.1)
            self._last_action = "type"

        elif action == "key":
            key_combo = params.get("text", "")
            self._execute_key(key_combo)
            # Spotlight needs extra time to appear after Cmd+Space
            lower_combo = key_combo.lower()
            if "space" in lower_combo and ("cmd" in lower_combo or "command" in lower_combo or "super" in lower_combo or "meta" in lower_combo):
                self._spotlight_active = True
                self._spotlight_typed = ""
                time.sleep(0.5)
            elif lower_combo in ("escape", "esc"):
                self._spotlight_active = False
            # After typing in Spotlight, Return opens an app — wait for it to launch
            elif lower_combo in ("return", "enter") and self._last_action == "type":
                # Resolve app name from Spotlight typed text before PID polling
                if self._spotlight_active and self._spotlight_typed:
                    resolved = self._resolve_app_name(self._spotlight_typed)
                    self._target_app_name = resolved or self._spotlight_typed
                    logger.info("Spotlight app resolved: %r → %r", self._spotlight_typed, self._target_app_name)
                self._spotlight_active = False

                old_pid = self._get_frontmost_pid()
                for _ in range(6):  # poll up to 3 seconds
                    time.sleep(0.5)
                    new_pid = self._get_frontmost_pid()
                    if new_pid and new_pid != old_pid:
                        self._target_app_pid = new_pid
                        logger.info("New app detected: PID %d (was %s)", new_pid, old_pid)
                        break
                else:
                    logger.warning("Frontmost app did not change after Return (still PID %s)", old_pid)
                    # Fallback: find PID by app name
                    if self._target_app_name:
                        found_pid = self._ax._find_app_pid(self._target_app_name)
                        if found_pid:
                            self._target_app_pid = found_pid
                            logger.info("Found target app PID by name %r: %d", self._target_app_name, found_pid)
            time.sleep(0.2)
            self._last_action = "key"

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

    def _action_key(self, action: str, params: dict) -> str:
        """Create a hashable key for an action to detect repetition.

        Coordinates are rounded to the nearest 20px so near-miss clicks
        (e.g. [1130, 633] vs [1130, 635]) are treated as the same action.
        """
        if "coordinate" in params:
            c = params["coordinate"]
            # Round to nearest 20px grid for fuzzy matching
            rx, ry = round(c[0] / 20) * 20, round(c[1] / 20) * 20
            return f"{action}@{rx},{ry}"
        if "text" in params:
            return f"{action}:{params['text']}"
        return action

    @staticmethod
    def _get_frontmost_app() -> str | None:
        """Get the name of the frontmost application via AppleScript."""
        try:
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _get_window_title() -> str | None:
        """Get the title of the front window via AppleScript."""
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of front window of first application process whose frontmost is true'],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _get_frontmost_pid() -> int | None:
        """Get PID of the frontmost application using NSWorkspace."""
        try:
            from AppKit import NSWorkspace
            front_app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if front_app:
                return front_app.processIdentifier()
        except Exception:
            pass
        return None

    @staticmethod
    def _resolve_app_name(typed: str) -> str | None:
        """Resolve a Spotlight-typed string to a running application's localized name.

        Matching priority: exact (case-insensitive) → bundle name → substring.
        """
        try:
            from AppKit import NSWorkspace
            apps = NSWorkspace.sharedWorkspace().runningApplications()
            typed_lower = typed.strip().lower()
            # 1. Exact match on localizedName (case-insensitive)
            for app in apps:
                name = app.localizedName()
                if name and name.lower() == typed_lower:
                    return name
            # 2. Bundle name match (e.g., "chrome" → "Google Chrome" via bundle id)
            for app in apps:
                bid = app.bundleIdentifier() or ""
                # Last component of bundle id, e.g. com.google.Chrome → chrome
                bundle_short = bid.rsplit(".", 1)[-1].lower() if bid else ""
                if bundle_short == typed_lower:
                    return app.localizedName()
            # 3. Substring match (e.g., "chrome" in "Google Chrome")
            for app in apps:
                name = app.localizedName()
                if name and typed_lower in name.lower():
                    return name
        except Exception as exc:
            logger.debug("_resolve_app_name failed: %s", exc)
        return None

    @staticmethod
    def _activate_pid(pid: int) -> bool:
        """Activate (bring to front) the application with the given PID."""
        try:
            from AppKit import NSWorkspace, NSRunningApplication
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if app.processIdentifier() == pid:
                    app.activateWithOptions_(1 << 1)  # NSApplicationActivateIgnoringOtherApps
                    time.sleep(0.3)
                    return True
        except Exception as exc:
            logger.debug("Failed to activate PID %d: %s", pid, exc)
        return False

    def _get_ax_summary(self, app_name: str | None) -> str | None:
        """Get AX tree summary for the given app (or frontmost), or None on failure."""
        # Strategy 1: If app_name given, try name-based lookup
        if app_name:
            try:
                tree = self._ax.get_ui_tree(app_name)
                if tree:
                    text = tree.to_text()
                    logger.info("AX tree for %s: %d chars", app_name, len(text))
                    return text[:4000]
            except Exception as exc:
                logger.debug("AX tree failed for %s: %s", app_name, exc)

        # Strategy 2: Use tracked target app PID (launched via Spotlight)
        if self._target_app_pid:
            try:
                tree = self._ax.get_ui_tree_by_pid(self._target_app_pid)
                if tree:
                    text = tree.to_text()
                    logger.info("AX tree for target PID %d: %d chars", self._target_app_pid, len(text))
                    return text[:4000]
            except Exception as exc:
                logger.debug("AX tree failed for target PID %d: %s", self._target_app_pid, exc)

        # Strategy 3: Use frontmost app PID (skip if it's the host IDE)
        pid = self._get_frontmost_pid()
        if pid and pid != self._host_pid:
            try:
                tree = self._ax.get_ui_tree_by_pid(pid)
                if tree:
                    text = tree.to_text()
                    logger.info("AX tree for frontmost PID %d: %d chars", pid, len(text))
                    return text[:4000]
            except Exception as exc:
                logger.debug("AX tree failed for PID %d: %s", pid, exc)

        # Strategy 4: Fallback — use frontmost PID even if it's the host
        if pid:
            try:
                tree = self._ax.get_ui_tree_by_pid(pid)
                if tree:
                    text = tree.to_text()
                    logger.info("AX tree for frontmost PID %d (host): %d chars", pid, len(text))
                    return text[:4000]
            except Exception as exc:
                logger.debug("AX tree failed for PID %d: %s", pid, exc)

        return None

    def _trim_with_summary(self, messages: list[dict]) -> list[dict]:
        """Trim message history while preserving an action summary."""
        if len(messages) <= 20:
            return messages

        n_dropped = len(messages) - 19
        summary_lines = [f"[Previous {n_dropped // 2} steps summarized]"]
        for entry in self._action_log[: n_dropped // 2]:
            summary_lines.append(f"- {entry}")
        summary_text = "\n".join(summary_lines)

        summary_msg = {"role": "user", "content": [{"type": "text", "text": summary_text}]}
        ack_msg = {"role": "assistant", "content": [{"type": "text", "text": "Understood, I'll build on what was already tried."}]}

        return [messages[0], summary_msg, ack_msg] + messages[-16:]

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

    def run(self, instruction: str, app_name: str | None = None) -> str:
        """Run synchronously."""
        return asyncio.run(self.arun(instruction, app_name))

    async def arun(self, instruction: str, app_name: str | None = None) -> str:
        """Run the computer use agent loop."""
        logger.info("Starting computer-use agent: %s", instruction)

        if app_name:
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

            # Trim history with action summary to avoid context overflow
            trimmed = self._trim_with_summary(messages)

            # Build API call kwargs
            api_kwargs: dict = dict(
                model=self._config.model,
                max_tokens=16384,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=trimmed,
                betas=["computer-use-2025-11-24"],
            )
            if self._thinking_supported:
                api_kwargs["thinking"] = {"type": "enabled", "budget_tokens": 4096}

            try:
                response = self._client.beta.messages.create(**api_kwargs)
            except Exception as exc:
                if self._thinking_supported:
                    logger.warning("Extended thinking failed, disabling: %s", exc)
                    self._thinking_supported = False
                    api_kwargs.pop("thinking", None)
                    api_kwargs["max_tokens"] = 4096
                    response = self._client.beta.messages.create(**api_kwargs)
                else:
                    raise

            assistant_content = response.content
            # Strip thinking blocks to avoid API errors on re-send
            content_for_history = [
                b for b in assistant_content
                if getattr(b, "type", None) not in ("thinking", "redacted_thinking")
            ]
            messages.append({"role": "assistant", "content": content_for_history})

            # If model finished without tool use
            if response.stop_reason == "end_turn":
                text_parts = [
                    b.text for b in assistant_content
                    if getattr(b, "type", None) == "text"
                ]
                return "\n".join(text_parts) if text_parts else "Agent finished."

            # Process tool uses
            tool_results: list[dict] = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                action = block.input.get("action", "")
                logger.info("Action: %s %s", action, {k: v for k, v in block.input.items() if k != "action"})

                # Track action for repetition detection
                key = self._action_key(action, block.input)
                self._action_keys.append(key)

                # Human-readable action description for history summary
                if action == "type":
                    self._action_log.append(f"typed: {block.input.get('text', '')}")
                elif action == "key":
                    self._action_log.append(f"pressed: {block.input.get('text', '')}")
                elif "coordinate" in block.input:
                    c = block.input["coordinate"]
                    self._action_log.append(f"{action} at ({c[0]}, {c[1]})")
                else:
                    self._action_log.append(action)

                # Activate target app before GUI actions
                if action not in ("screenshot", "wait"):
                    if app_name:
                        self._activate_app(app_name)
                    elif self._target_app_name:
                        self._activate_app(self._target_app_name)
                    elif self._target_app_pid:
                        self._activate_pid(self._target_app_pid)

                error = self._dispatch_action(action, block.input)

                if error:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": error,
                        "is_error": True,
                    })
                else:
                    # Build content parts: context + warning + AX tree + screenshot
                    content_parts: list[dict] = []

                    # Current app / window context
                    current_app = self._get_frontmost_app()
                    window_title = self._get_window_title()
                    context_lines: list[str] = []
                    if current_app:
                        context_lines.append(f"Current App: {current_app}")
                    if window_title:
                        context_lines.append(f"Window Title: {window_title}")

                    # State change detection
                    if self._prev_app and current_app and current_app != self._prev_app:
                        context_lines.append(f"NOTE: App changed from '{self._prev_app}' to '{current_app}'")
                    if self._prev_window and window_title and window_title != self._prev_window:
                        context_lines.append(f"NOTE: Window changed to '{window_title}'")
                    if (action in ("left_click", "type", "key", "double_click")
                            and self._prev_app and current_app == self._prev_app
                            and self._prev_window and window_title == self._prev_window):
                        context_lines.append("NOTE: No visible window change detected after this action.")

                    self._prev_app = current_app
                    self._prev_window = window_title

                    if context_lines:
                        content_parts.append({"type": "text", "text": "\n".join(context_lines)})

                    # Repetition warning (threshold: 2)
                    recent = self._action_keys[-5:]
                    repeat_count = recent.count(key)
                    if repeat_count >= 2:
                        content_parts.append({
                            "type": "text",
                            "text": f"WARNING: You have attempted '{action}' {repeat_count} times recently. This is NOT working. You MUST try a COMPLETELY different approach.",
                        })
                        logger.warning("Repetition detected: %s ×%d", key, repeat_count)

                    # AX tree summary
                    ax_text = self._get_ax_summary(app_name or self._target_app_name)
                    if ax_text:
                        content_parts.append({"type": "text", "text": f"UI Elements:\n{ax_text}"})

                    # Screenshot
                    screenshot_b64 = self._take_screenshot_b64()
                    content_parts.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content_parts,
                    })

            messages.append({"role": "user", "content": tool_results})

        return "Agent reached maximum steps without completing the task."

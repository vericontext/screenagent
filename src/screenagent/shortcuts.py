"""Shortcut functions for common operations — no API key required."""

from __future__ import annotations

from screenagent.types import Rect, UIElement


def screenshot(region: Rect | None = None) -> bytes:
    """Capture a screenshot. Returns PNG bytes."""
    from screenagent.perception.screenshot import ScreenshotPerceiver
    return ScreenshotPerceiver().screenshot(region)


def click(x: float, y: float) -> None:
    """Click at screen coordinates (x, y)."""
    from screenagent.action.cgevent import CGEventActor
    CGEventActor().click(x, y)


def double_click(x: float, y: float) -> None:
    """Double-click at screen coordinates (x, y)."""
    from screenagent.action.cgevent import CGEventActor
    CGEventActor().double_click(x, y)


def type_text(text: str) -> None:
    """Type a string character by character."""
    from screenagent.action.cgevent import CGEventActor
    CGEventActor().type_text(text)


def key_press(key: str, modifiers: list[str] | None = None) -> None:
    """Press a key with optional modifiers (e.g. key_press("l", ["command"]))."""
    from screenagent.action.cgevent import CGEventActor
    CGEventActor().key_press(key, modifiers)


def scroll(x: float, y: float, dx: float, dy: float) -> None:
    """Scroll at position (x, y) by (dx, dy) pixels."""
    from screenagent.action.cgevent import CGEventActor
    CGEventActor().scroll(x, y, dx, dy)


def get_ui_tree(app_name: str) -> UIElement | None:
    """Read the accessibility tree for a running application."""
    from screenagent.perception.ax import AXPerceiver
    return AXPerceiver().get_ui_tree(app_name)

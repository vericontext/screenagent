"""screenagent — macOS GUI Automation Framework."""

from screenagent.types import Rect, UIElement, ScreenState, ToolResult
from screenagent.interfaces import Perceiver, Actor, BrowserPerceiver, BrowserActor
from screenagent.config import Config

__all__ = [
    "Rect",
    "UIElement",
    "ScreenState",
    "ToolResult",
    "Perceiver",
    "Actor",
    "BrowserPerceiver",
    "BrowserActor",
    "Config",
]

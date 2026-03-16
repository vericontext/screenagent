"""screenagent — Computer Use SDK for Python."""

from __future__ import annotations

from importlib.metadata import version, PackageNotFoundError

from screenagent.types import Rect, UIElement, ScreenState, ToolResult, AgentResult
from screenagent.interfaces import Perceiver, Actor, BrowserPerceiver, BrowserActor
from screenagent.config import Config
from screenagent.sdk import Agent
from screenagent.shortcuts import (
    screenshot,
    click,
    double_click,
    type_text,
    key_press,
    scroll,
    get_ui_tree,
)

try:
    __version__ = version("screenagent")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    # SDK
    "Agent",
    "AgentResult",
    "__version__",
    # Types
    "Rect",
    "UIElement",
    "ScreenState",
    "ToolResult",
    # Protocols
    "Perceiver",
    "Actor",
    "BrowserPerceiver",
    "BrowserActor",
    # Config
    "Config",
    # Shortcuts
    "screenshot",
    "click",
    "double_click",
    "type_text",
    "key_press",
    "scroll",
    "get_ui_tree",
]

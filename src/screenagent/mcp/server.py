"""FastMCP server wrapping the screenagent agent."""

from __future__ import annotations

import base64

from mcp.server.fastmcp import FastMCP

from screenagent.config import Config
from screenagent.agent.loop import AgentLoop
from screenagent.perception.ax import AXPerceiver
from screenagent.perception.screenshot import ScreenshotPerceiver

mcp = FastMCP("screenagent")


def _get_config() -> Config:
    return Config.from_env()


@mcp.tool()
def automate_gui(instruction: str, app_name: str = "Google Chrome") -> str:
    """Run a GUI automation task. The agent will perceive the screen and execute
    actions to complete the instruction.

    Args:
        instruction: Natural language instruction for what to do.
        app_name: Target application name (default: Google Chrome).
    """
    config = _get_config()
    agent = AgentLoop(config)
    return agent.run(instruction, app_name)


@mcp.tool()
def screenshot() -> str:
    """Capture a screenshot of the current screen. Returns base64-encoded PNG."""
    s = ScreenshotPerceiver()
    png = s.screenshot()
    return base64.b64encode(png).decode()


@mcp.tool()
def get_accessibility_tree(app_name: str) -> str:
    """Get the accessibility UI tree of an application.

    Args:
        app_name: The application name (e.g. 'Google Chrome', 'Finder').
    """
    ax = AXPerceiver()
    tree = ax.get_ui_tree(app_name)
    if tree is None:
        return f"Could not get UI tree for {app_name!r}. Is the app running?"
    return tree.to_text()


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

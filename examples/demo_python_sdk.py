#!/usr/bin/env python3
"""Demo: screenagent Python SDK

Run sections one by one to showcase SDK capabilities.
Sections 1-2 work without an API key.

Usage:
    uv run python examples/demo_python_sdk.py [section]

Sections:
    1  Screenshot + AX tree (no API key)
    2  Direct mouse/keyboard  (no API key)
    3  3-line agent           (requires ANTHROPIC_API_KEY)
    4  Agent with target app  (requires ANTHROPIC_API_KEY)
    5  Custom loop            (requires ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import sys


# ── Section 1: Perception (no API key) ──────────────────────────

def section_screenshot_and_ax():
    """Capture screen and read UI tree."""
    from screenagent import screenshot, get_ui_tree

    # Screenshot
    png = screenshot()
    path = "/tmp/screenagent_demo.png"
    with open(path, "wb") as f:
        f.write(png)
    print(f"Screenshot saved: {path} ({len(png):,} bytes)")

    # Accessibility tree
    tree = get_ui_tree("Finder")
    if tree:
        print("\nFinder UI tree:")
        print(tree.to_text()[:2000])
    else:
        print("Could not read Finder UI tree (check Accessibility permissions)")


# ── Section 2: Direct actions (no API key) ──────────────────────

def section_direct_actions():
    """Click, type, and press keys directly."""
    from screenagent import click, type_text, key_press

    print("Clicking at (640, 400)...")
    click(640, 400)

    print("Typing 'hello from screenagent'...")
    type_text("hello from screenagent")

    print("Pressing Return...")
    key_press("return")

    print("Done.")


# ── Section 3: 3-line agent ─────────────────────────────────────

def section_basic_agent():
    """The simplest possible agent usage."""
    from screenagent import Agent

    agent = Agent()
    result = agent.run("Open Calculator and compute 256 + 512")

    print(f"Summary: {result.summary}")
    print(f"Success: {result.success}")
    print(f"Steps:   {result.steps}")


# ── Section 4: Agent with target app ────────────────────────────

def section_targeted_agent():
    """Agent focused on a specific application."""
    from screenagent import Agent

    agent = Agent(app="System Settings", max_steps=15)
    result = agent.run("Switch the appearance to Dark Mode")

    print(f"Summary: {result.summary}")
    print(f"Success: {result.success}")
    print(f"Steps:   {result.steps}")


# ── Section 5: Custom loop ──────────────────────────────────────

def section_custom_loop():
    """Direct loop control for advanced use cases."""
    from screenagent import Config
    from screenagent.agent.computer_use import ComputerUseLoop

    config = Config.from_env()
    config.computer_use = True
    config.max_steps = 10

    loop = ComputerUseLoop(config=config)
    summary = loop.run(
        "Open Notes and create a note titled 'screenagent demo'",
        app_name="Notes",
    )
    print(f"Result: {summary}")


# ── Runner ──────────────────────────────────────────────────────

SECTIONS = {
    "1": ("Screenshot + AX tree", section_screenshot_and_ax),
    "2": ("Direct actions", section_direct_actions),
    "3": ("3-line agent", section_basic_agent),
    "4": ("Agent with target app", section_targeted_agent),
    "5": ("Custom loop", section_custom_loop),
}


def main():
    choice = sys.argv[1] if len(sys.argv) > 1 else None

    if choice and choice in SECTIONS:
        name, fn = SECTIONS[choice]
        print(f"=== Section {choice}: {name} ===\n")
        fn()
        return

    # No arg or invalid — show menu
    print(__doc__)
    print("Available sections:")
    for k, (name, _) in SECTIONS.items():
        api = "" if k in ("1", "2") else " (needs API key)"
        print(f"  {k}. {name}{api}")
    print()

    if choice is None:
        print("Pass a section number: uv run python examples/demo_python_sdk.py 1")
    else:
        print(f"Unknown section: {choice}")


if __name__ == "__main__":
    main()

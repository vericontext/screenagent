"""Tool schema definitions for Claude tool_use."""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "screenshot",
        "description": "Capture a screenshot of the current screen. Returns the screenshot as an image.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_ui_tree",
        "description": "Get the accessibility UI tree of an application. Returns a text representation of UI elements.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "The name of the application (e.g. 'Google Chrome', 'Finder')",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "click",
        "description": "Click at the specified screen coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "number", "description": "X coordinate"},
                "y": {"type": "number", "description": "Y coordinate"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text using the keyboard. The text will be typed character by character.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to type"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "key_press",
        "description": "Press a key, optionally with modifiers. Keys: return, tab, space, escape, delete, left, right, up, down, a-z, f1-f8. Modifiers: command, shift, option, control.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name"},
                "modifiers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Modifier keys (e.g. ['command', 'shift'])",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll at the specified position.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "number", "description": "X coordinate to scroll at"},
                "y": {"type": "number", "description": "Y coordinate to scroll at"},
                "dx": {"type": "number", "description": "Horizontal scroll amount (pixels)"},
                "dy": {"type": "number", "description": "Vertical scroll amount (pixels, negative=down)"},
            },
            "required": ["x", "y", "dx", "dy"],
        },
    },
    {
        "name": "navigate",
        "description": "Navigate the browser to a URL. Requires Chrome running with remote debugging.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "open_url",
        "description": "Navigate browser to a URL using keyboard (Cmd+L → type URL → Enter). Works without CDP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "done",
        "description": "Call this when the task is complete. Provide a summary of what was accomplished.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Summary of what was done"},
            },
            "required": ["summary"],
        },
    },
]

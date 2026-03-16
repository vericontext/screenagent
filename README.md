# screenagent

**Control any macOS app with Claude — Python SDK + CLI.**

<!-- Replace with actual GIF after recording -->
![demo](https://via.placeholder.com/800x400?text=screenagent+demo+GIF)

Browser Use and Skyvern only work inside the browser.
screenagent uses macOS Accessibility API + CGEvent for native input, so it works with **System Settings, Finder, Notes, Calculator, and any app**.

## Install

```bash
pip install screenagent-ai
```

This installs both the Python SDK (`from screenagent import ...`) and the `screenagent` CLI command.

Requires macOS and Python 3.11+.

## Setup

### 1. Anthropic API Key

Get your key at [console.anthropic.com](https://console.anthropic.com/) and set it:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 2. Accessibility Permission

macOS requires you to grant accessibility access to your terminal app:

**System Settings → Privacy & Security → Accessibility** → add your terminal (Terminal.app, iTerm2, VS Code, etc.)

Without this, screenagent cannot read UI elements or send keyboard/mouse events.

## Usage 1: CLI

Run directly from the terminal. Works with Claude Code out of the box.

```bash
# Control native apps (finds and launches via Spotlight automatically)
screenagent run "Open Calculator and compute 42 * 17"
screenagent run "Open System Settings and switch to Dark Mode"

# Browser automation
screenagent run "Open Chrome, go to youtube.com, search for ycombinator"
screenagent run --app "Google Chrome" "Go to google.com and search for AI news"

# Individual actions (no API key needed)
screenagent screenshot --file screen.png
screenagent ax-tree "Google Chrome"
screenagent click 640 400
screenagent type "hello world"
screenagent key return --modifiers command
```

## Usage 2: Python SDK

### 3-line agent

```python
from screenagent import Agent

agent = Agent()
result = agent.run("Open System Settings and switch to Dark Mode")
print(result.summary)
print(result.success)
```

### Component functions (no API key needed)

```python
from screenagent import screenshot, click, type_text, key_press, get_ui_tree

png_bytes = screenshot()
click(640, 400)
type_text("hello world")
key_press("return")

tree = get_ui_tree("Google Chrome")
print(tree.to_text())
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Claude API key (required for agent) |
| `AGENT_MODEL` | `claude-sonnet-4-6` | Model to use |
| `AGENT_MAX_STEPS` | `20` | Maximum agent loop iterations |
| `AGENT_COMPUTER_USE` | `true` | Use Claude computer-use tool |
| `CDP_PORT` | `9222` | Chrome DevTools Protocol port |

Also supports `.env` files.

## License

MIT

# screenagent

**3 lines to control any macOS app with Claude.**

<!-- Replace with actual GIF after recording -->
![demo](https://via.placeholder.com/800x400?text=screenagent+demo+GIF)

```python
from screenagent import Agent
agent = Agent()
result = agent.run("Switch to Dark Mode on Mac")
```

## Why screenagent?

| | screenagent | Browser Use | Skyvern | ScreenPipe | Open Interpreter |
|---|---|---|---|---|---|
| **Native macOS apps** | Yes | No | No | Record only | Partial (shell) |
| **Browser control** | Yes (CDP) | Yes | Yes | No | No |
| **Accessibility tree** | Yes | No | No | No | No |
| **Native input (CGEvent)** | Yes | No | No | No | No |
| **SDK (import & use)** | Yes | Yes | API only | Yes | No |
| **3-line quickstart** | Yes | No | No | No | No |

Browser Use and Skyvern only work inside the browser.
screenagent uses macOS Accessibility APIs + CGEvent for native input, so it works with **Finder, System Settings, Notes, or any app**.

## Install

```bash
pip install screenagent
```

Requires macOS and Python 3.11+.

## Quick Start

### 3-line agent

```python
from screenagent import Agent

agent = Agent()
result = agent.run("Search for 'screenagent' on google.com")
print(result.summary)   # what the agent accomplished
print(result.success)   # True / False
```

### Component functions (no API key)

```python
from screenagent import screenshot, click, type_text, key_press, get_ui_tree

# Capture the screen
png_bytes = screenshot()

# Click, type, press keys
click(640, 400)
type_text("hello world")
key_press("return")

# Read accessibility tree
tree = get_ui_tree("Google Chrome")
print(tree.to_text())
```

### Custom loop with Protocols

```python
from screenagent import Config
from screenagent.agent.loop import AgentLoop

config = Config.from_env()
config.computer_use = False
config.max_steps = 10

loop = AgentLoop(config=config)
summary = loop.run("Open System Settings and go to Displays")
```

## How It Works

screenagent combines **3 perception channels** and **2 action channels** to give Claude full control of your Mac:

**Perception:**
- **Screenshot** — pixel-level screen capture via Quartz
- **Accessibility tree** — structured UI elements (buttons, labels, text fields) via macOS AX API
- **CDP DOM** — browser page structure and JavaScript evaluation via Chrome DevTools Protocol

**Action:**
- **CGEvent** — native macOS mouse clicks, keyboard input, and scrolling
- **CDP commands** — browser navigation, element clicking, and JS execution

## Architecture

```
screenagent/
├── sdk.py          # Agent — high-level entry point
├── shortcuts.py    # screenshot, click, type_text, ...
├── config.py       # Config.from_env()
├── interfaces.py   # Perceiver / Actor protocols
├── perception/     # ScreenshotPerceiver, AXPerceiver, CDPPerceiver
├── action/         # CGEventActor, CDPActor
└── agent/          # AgentLoop (tool-use), ComputerUseLoop (computer-use)
```

## CLI

```bash
screenagent run "Search for AI news on google.com"
screenagent screenshot --file screen.png
screenagent ax-tree "Google Chrome"
screenagent click 640 400
screenagent type "hello"
screenagent key return --modifiers command
screenagent check          # diagnose CDP connectivity
screenagent schema         # dump tool JSON schemas
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Claude API key (required for agent) |
| `AGENT_MODEL` | `claude-sonnet-4-6` | Model to use |
| `AGENT_MAX_STEPS` | `20` | Maximum agent loop iterations |
| `AGENT_COMPUTER_USE` | `true` | Use native computer-use tool |
| `CDP_PORT` | `9222` | Chrome DevTools Protocol port |

Or pass a `.env` file in the current directory.

## Requirements

- macOS (Quartz CGEvent, Accessibility API)
- Python 3.11+
- Accessibility permission granted to your terminal/IDE
- Chrome with `--remote-debugging-port=9222` for CDP features (optional)

## License

MIT

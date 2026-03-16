#!/usr/bin/env bash
# Demo: screenagent from Claude Code / CLI
#
# Run each section interactively to demonstrate capabilities.
# No API key needed for sections 1-2. Section 3+ requires ANTHROPIC_API_KEY.

set -euo pipefail

echo "================================================"
echo "  screenagent CLI Demo"
echo "================================================"
echo

# ------------------------------------------------------------------
# Section 1: Perception (no API key required)
# ------------------------------------------------------------------
echo "--- 1. Screenshot ---"
uv run screenagent screenshot --file /tmp/screenagent_demo.png
echo "Saved to /tmp/screenagent_demo.png"
echo

echo "--- 2. Accessibility Tree ---"
uv run screenagent ax-tree "Finder" --fields role,title
echo

# ------------------------------------------------------------------
# Section 2: Direct actions (no API key required)
# ------------------------------------------------------------------
echo "--- 3. Click + Type ---"
# Uncomment to execute:
# uv run screenagent click 640 400
# uv run screenagent type "hello from screenagent"
# uv run screenagent key return
echo "(Uncomment lines above to run)"
echo

# ------------------------------------------------------------------
# Section 3: Agent runs (requires ANTHROPIC_API_KEY)
# ------------------------------------------------------------------
echo "--- 4. Dry-run (validate config) ---"
uv run screenagent run --dry-run "Switch to Dark Mode"
echo

echo "--- 5. Native app control ---"
echo "Uncomment ONE of the following to run:"
echo
echo '  # Dark Mode toggle (visual impact)'
echo '  uv run screenagent run "Open System Settings and switch to Dark Mode"'
echo
echo '  # Calculator (simple, reliable)'
echo '  uv run screenagent run "Open Calculator and compute 1024 * 768"'
echo
echo '  # Notes app'
echo '  uv run screenagent run "Open Notes and create a note titled Demo with 3 bullet points about AI agents"'
echo

echo "--- 6. Browser automation (requires Chrome with CDP) ---"
echo '  uv run screenagent run --app "Google Chrome" "Go to google.com and search for screenagent"'
echo

echo "--- 7. JSON output (for programmatic use) ---"
uv run screenagent --output json run --dry-run "test task"
echo

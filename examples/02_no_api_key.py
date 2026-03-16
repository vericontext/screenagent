"""Component functions that work without an API key.

Demonstrates screenshot capture, mouse/keyboard input,
and accessibility tree reading.
"""

from screenagent import screenshot, click, type_text, key_press, get_ui_tree

# 1. Capture screenshot
png = screenshot()
print(f"Screenshot: {len(png)} bytes")

# 2. Read accessibility tree for Finder
tree = get_ui_tree("Finder")
if tree:
    print(tree.to_text())
else:
    print("Could not read Finder UI tree (check Accessibility permissions)")

# 3. Click and type (uncomment to actually perform actions)
# click(640, 400)
# type_text("hello world")
# key_press("return")

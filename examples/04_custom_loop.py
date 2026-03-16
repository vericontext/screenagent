"""Custom agent loop using the Protocol interfaces.

Shows how to use AgentLoop or ComputerUseLoop directly
with custom configuration.

Requires: ANTHROPIC_API_KEY environment variable.
"""

from screenagent import Config
from screenagent.agent.loop import AgentLoop
from screenagent.agent.computer_use import ComputerUseLoop

# --- Option A: Tool-use mode (AgentLoop) ---
config = Config.from_env()
config.computer_use = False
config.max_steps = 5

loop = AgentLoop(config=config)
# summary = loop.run("Open Safari and go to apple.com", app_name="Safari")
# print(summary)

# --- Option B: Computer-use mode (ComputerUseLoop) ---
config2 = Config.from_env()
config2.computer_use = True
config2.max_steps = 10

loop2 = ComputerUseLoop(config=config2)
# summary2 = loop2.run("Take a screenshot and describe what you see")
# print(summary2)

print("Examples configured — uncomment the run() calls to execute.")

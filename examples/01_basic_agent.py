"""Basic agent — 3 lines to run a computer-use task.

Requires: ANTHROPIC_API_KEY environment variable.
"""

from screenagent import Agent

agent = Agent()
result = agent.run("Search for 'screenagent' on google.com")

print(f"Summary: {result.summary}")
print(f"Success: {result.success}")
print(f"Steps:   {result.steps}")

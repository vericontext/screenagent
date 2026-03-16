#!/usr/bin/env python3
"""Demo recording script — Dark Mode toggle.

Run this while screen-recording to capture the demo GIF.
Shows a 3-second countdown, then executes the agent.
"""

import sys
import time

from screenagent import Agent


def countdown(seconds: int = 3) -> None:
    for i in range(seconds, 0, -1):
        print(f"  Starting in {i}...", flush=True)
        time.sleep(1)
    print()


def main() -> None:
    print("=" * 50)
    print("  screenagent — Demo Recording")
    print("=" * 50)
    print()

    # Show the code being executed (REPL style)
    print(">>> from screenagent import Agent")
    print(">>> agent = Agent()")
    print('>>> result = agent.run("Switch to Dark Mode on Mac")')
    print()

    countdown()

    agent = Agent()
    result = agent.run("Switch to Dark Mode on Mac")

    print()
    print(f">>> result.summary")
    print(result.summary)
    print()
    print(f">>> result.steps")
    print(result.steps)
    print()
    print(f">>> result.success")
    print(result.success)


if __name__ == "__main__":
    main()

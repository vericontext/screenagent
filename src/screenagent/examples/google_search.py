"""Demo: Open Chrome, navigate to google.com, search for 'MCP protocol'."""

from __future__ import annotations

import logging
import subprocess
import sys
import time

from screenagent.config import Config
from screenagent.agent.loop import AgentLoop


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    config = Config.from_env()
    if not config.anthropic_api_key:
        print("Error: ANTHROPIC_API_KEY not set. Export it or add to .env", file=sys.stderr)
        sys.exit(1)

    # Launch Chrome with remote debugging if not already running
    print("Launching Chrome with remote debugging...")
    subprocess.Popen(
        [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            f"--remote-debugging-port={config.cdp_port}",
            "--user-data-dir=/tmp/chrome-debug-profile",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)

    agent = AgentLoop(config)
    instruction = "Open google.com and search for 'MCP protocol'"
    print(f"Running agent with instruction: {instruction}")

    result = agent.run(instruction, app_name="Google Chrome")
    print(f"\nResult: {result}")


if __name__ == "__main__":
    main()

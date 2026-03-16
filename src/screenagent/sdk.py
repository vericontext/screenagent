"""High-level SDK interface for screenagent."""

from __future__ import annotations

import asyncio

from screenagent.config import Config
from screenagent.types import AgentResult


class Agent:
    """High-level agent that runs computer-use or tool-use loops.

    Usage::

        from screenagent import Agent
        agent = Agent()
        result = agent.run("Search for 'screenagent' on google.com")
        print(result.summary)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_steps: int | None = None,
        app: str | None = None,
        computer_use: bool | None = None,
    ):
        cfg = Config.from_env()
        if api_key is not None:
            cfg.anthropic_api_key = api_key
        if model is not None:
            cfg.model = model
        if max_steps is not None:
            cfg.max_steps = max_steps
        if computer_use is not None:
            cfg.computer_use = computer_use

        self._config = cfg
        self._app = app

    def _ensure_api_key(self) -> None:
        if not self._config.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required. "
                "Set it via environment variable, .env file, or Agent(api_key='...')"
            )

    def _make_loop(self):
        """Create the appropriate loop based on config."""
        if self._config.computer_use:
            from screenagent.agent.computer_use import ComputerUseLoop
            return ComputerUseLoop(config=self._config)
        else:
            from screenagent.agent.loop import AgentLoop
            return AgentLoop(config=self._config)

    def run(self, instruction: str, *, app: str | None = None) -> AgentResult:
        """Run the agent synchronously and return a structured result."""
        self._ensure_api_key()
        loop = self._make_loop()
        app_name = app if app is not None else self._app
        summary = loop.run(instruction, app_name=app_name)
        return AgentResult(
            summary=summary,
            steps=getattr(loop, "_step_count", 0),
            success="reached maximum steps" not in summary.lower(),
        )

    async def arun(self, instruction: str, *, app: str | None = None) -> AgentResult:
        """Run the agent asynchronously and return a structured result."""
        self._ensure_api_key()
        loop = self._make_loop()
        app_name = app if app is not None else self._app
        summary = await loop.arun(instruction, app_name=app_name)
        return AgentResult(
            summary=summary,
            steps=getattr(loop, "_step_count", 0),
            success="reached maximum steps" not in summary.lower(),
        )

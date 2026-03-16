"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    anthropic_api_key: str = ""
    cdp_port: int = 9222
    max_steps: int = 20
    model: str = "claude-sonnet-4-20250514"

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            cdp_port=int(os.environ.get("CDP_PORT", "9222")),
            max_steps=int(os.environ.get("AGENT_MAX_STEPS", "20")),
            model=os.environ.get("AGENT_MODEL", "claude-sonnet-4-20250514"),
        )


def create_components(config: Config | None = None):
    """Factory function that wires perception and action implementations."""
    if config is None:
        config = Config.from_env()

    from screenagent.perception.composite import CompositePerceiver
    from screenagent.action.cgevent import CGEventActor

    perceiver = CompositePerceiver(cdp_port=config.cdp_port)
    actor = CGEventActor()
    return perceiver, actor

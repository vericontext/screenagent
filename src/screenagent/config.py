"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env file from CWD into os.environ (without overwriting existing vars)."""
    env_path = Path.cwd() / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        # Don't overwrite already-set env vars
        if key not in os.environ:
            os.environ[key] = value


@dataclass
class Config:
    anthropic_api_key: str = ""
    cdp_port: int = 9222
    max_steps: int = 20
    model: str = "claude-haiku-4-5-20251001"

    @classmethod
    def from_env(cls) -> Config:
        _load_dotenv()
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            cdp_port=int(os.environ.get("CDP_PORT", "9222")),
            max_steps=int(os.environ.get("AGENT_MAX_STEPS", "20")),
            model=os.environ.get("AGENT_MODEL", "claude-haiku-4-5-20251001"),
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

"""Tests for agent loop with mocked Claude client."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass

import pytest

from screenagent.agent.tools import TOOLS
from screenagent.agent.loop import AgentLoop
from screenagent.config import Config
from screenagent.types import ScreenState


class TestToolDefinitions:
    def test_all_tools_have_required_fields(self):
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_tool_names_unique(self):
        names = [t["name"] for t in TOOLS]
        assert len(names) == len(set(names))

    def test_expected_tools_present(self):
        names = {t["name"] for t in TOOLS}
        expected = {"screenshot", "get_ui_tree", "click", "type_text", "key_press", "scroll", "navigate", "open_url", "done"}
        assert expected == names


@dataclass
class MockTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class MockToolUseBlock:
    type: str = "tool_use"
    id: str = "tool_1"
    name: str = ""
    input: dict = None

    def __post_init__(self):
        if self.input is None:
            self.input = {}


@dataclass
class MockResponse:
    content: list = None
    stop_reason: str = "tool_use"

    def __post_init__(self):
        if self.content is None:
            self.content = []


def _mock_screen_state():
    return ScreenState(
        app_name="Test",
        ui_tree=None,
        screenshot_png=None,
        url=None,
        dom_summary=None,
    )


class TestAgentLoop:
    @patch("screenagent.agent.loop.CompositePerceiver")
    @patch("screenagent.agent.loop.CGEventActor")
    @patch("screenagent.agent.loop.anthropic.Anthropic")
    def test_done_tool_exits_loop(self, mock_anthropic_cls, mock_actor_cls, mock_perceiver_cls):
        config = Config(anthropic_api_key="test-key", max_steps=5)

        # Mock perceiver with async method
        mock_perceiver = MagicMock()
        mock_perceiver._perceive_async = AsyncMock(return_value=_mock_screen_state())
        mock_perceiver.screenshot.return_value = b"fake-png"
        mock_perceiver_cls.return_value = mock_perceiver

        # Mock actor
        mock_actor_cls.return_value = MagicMock()

        # Mock Claude client
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # Claude responds with done tool
        mock_client.messages.create.return_value = MockResponse(
            content=[
                MockToolUseBlock(name="done", input={"summary": "Task completed successfully"}),
            ],
            stop_reason="tool_use",
        )

        agent = AgentLoop(config)
        result = agent.run("Do something", app_name="Test")
        assert result == "Task completed successfully"

    @patch("screenagent.agent.loop.CompositePerceiver")
    @patch("screenagent.agent.loop.CGEventActor")
    @patch("screenagent.agent.loop.anthropic.Anthropic")
    def test_max_steps_reached(self, mock_anthropic_cls, mock_actor_cls, mock_perceiver_cls):
        config = Config(anthropic_api_key="test-key", max_steps=2)

        mock_perceiver = MagicMock()
        mock_perceiver._perceive_async = AsyncMock(return_value=_mock_screen_state())
        mock_perceiver.screenshot.return_value = b"fake-png"
        mock_perceiver_cls.return_value = mock_perceiver
        mock_actor_cls.return_value = MagicMock()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # Claude keeps calling screenshot (never calls done)
        mock_client.messages.create.return_value = MockResponse(
            content=[MockToolUseBlock(name="screenshot", input={})],
            stop_reason="tool_use",
        )

        agent = AgentLoop(config)
        result = agent.run("Do something", app_name="Test")
        assert "maximum steps" in result

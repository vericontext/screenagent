"""Tests for open_url tool and navigate fallback."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, call

import pytest

from screenagent.agent.loop import AgentLoop
from screenagent.config import Config
from screenagent.types import ScreenState


def _mock_screen_state():
    return ScreenState(
        app_name="Test",
        ui_tree=None,
        screenshot_png=None,
        url=None,
        dom_summary=None,
    )


def _make_agent():
    """Create an AgentLoop with mocked dependencies."""
    with patch("screenagent.agent.loop.CompositePerceiver") as mock_perc_cls, \
         patch("screenagent.agent.loop.CGEventActor") as mock_actor_cls, \
         patch("screenagent.agent.loop.anthropic.Anthropic") as mock_api_cls:

        mock_perceiver = MagicMock()
        mock_perceiver._perceive_async = AsyncMock(return_value=_mock_screen_state())
        mock_perceiver.screenshot.return_value = b"fake-png"
        mock_perceiver._ensure_cdp = AsyncMock(return_value=False)
        mock_perc_cls.return_value = mock_perceiver

        mock_actor = MagicMock()
        mock_actor_cls.return_value = mock_actor

        mock_client = MagicMock()
        mock_api_cls.return_value = mock_client

        config = Config(anthropic_api_key="test-key", max_steps=5)
        agent = AgentLoop(config)

    return agent, mock_actor, mock_perceiver


class TestOpenUrl:
    def test_open_url_dispatches_keyboard_sequence(self):
        agent, mock_actor, _ = _make_agent()
        result = asyncio.run(agent._dispatch_tool("open_url", {"url": "https://example.com"}))

        assert result.output is not None
        assert "https://example.com" in result.output
        assert "keyboard" in result.output

        # Verify keyboard sequence: Cmd+L, Cmd+A, type_text, Enter
        calls = mock_actor.method_calls
        key_calls = [(c[0], c[1], c[2] if len(c) > 2 else {}) for c in calls]
        assert call.key_press("l", ["command"]) in calls
        assert call.key_press("a", ["command"]) in calls
        assert call.type_text("https://example.com") in calls
        assert call.key_press("return", None) in calls

    def test_open_url_returns_screenshot(self):
        agent, _, mock_perceiver = _make_agent()
        mock_perceiver.screenshot.return_value = b"screenshot-data"
        result = asyncio.run(agent._dispatch_tool("open_url", {"url": "https://example.com"}))

        assert result.screenshot_png == b"screenshot-data"


class TestNavigateFallback:
    def test_navigate_falls_back_when_cdp_unavailable(self):
        agent, mock_actor, _ = _make_agent()
        # CDP actor is None (not connected)
        result = asyncio.run(agent._dispatch_tool("navigate", {"url": "https://example.com"}))

        assert result.output is not None
        assert "keyboard" in result.output
        # Should have used keyboard sequence
        assert call.key_press("l", ["command"]) in mock_actor.method_calls

    def test_navigate_falls_back_on_cdp_error(self):
        agent, mock_actor, mock_perceiver = _make_agent()
        # Set up CDP actor that raises
        mock_perceiver._ensure_cdp = AsyncMock(return_value=True)
        mock_perceiver.cdp = MagicMock()

        mock_cdp_actor = MagicMock()
        mock_cdp_actor.navigate = AsyncMock(side_effect=RuntimeError("CDP error"))

        with patch("screenagent.agent.loop.CDPActor", return_value=mock_cdp_actor):
            agent._cdp_actor = mock_cdp_actor
            result = asyncio.run(agent._dispatch_tool("navigate", {"url": "https://example.com"}))

        assert result.output is not None
        assert "keyboard" in result.output

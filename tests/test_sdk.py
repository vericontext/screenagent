"""Tests for the SDK high-level Agent class."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from screenagent.sdk import Agent
from screenagent.types import AgentResult
from screenagent.config import Config


class TestAgentInit:
    def test_default_config_from_env(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            agent = Agent()
            assert agent._config.anthropic_api_key == "test-key"

    def test_override_api_key(self):
        agent = Agent(api_key="my-key")
        assert agent._config.anthropic_api_key == "my-key"

    def test_override_model(self):
        agent = Agent(api_key="k", model="claude-haiku-4-5-20251001")
        assert agent._config.model == "claude-haiku-4-5-20251001"

    def test_override_max_steps(self):
        agent = Agent(api_key="k", max_steps=5)
        assert agent._config.max_steps == 5

    def test_override_computer_use(self):
        agent = Agent(api_key="k", computer_use=False)
        assert agent._config.computer_use is False

    def test_default_app(self):
        agent = Agent(api_key="k")
        assert agent._app is None

    def test_custom_app(self):
        agent = Agent(api_key="k", app="Safari")
        assert agent._app == "Safari"


class TestAgentApiKeyValidation:
    def test_run_raises_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            agent = Agent(api_key="")
            try:
                agent.run("test")
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "ANTHROPIC_API_KEY" in str(e)


class TestAgentLoopSelection:
    def test_computer_use_true_selects_computer_use_loop(self):
        agent = Agent(api_key="k", computer_use=True)
        loop = agent._make_loop()
        from screenagent.agent.computer_use import ComputerUseLoop
        assert isinstance(loop, ComputerUseLoop)

    def test_computer_use_false_selects_agent_loop(self):
        agent = Agent(api_key="k", computer_use=False)
        loop = agent._make_loop()
        from screenagent.agent.loop import AgentLoop
        assert isinstance(loop, AgentLoop)


class TestAgentResult:
    def test_defaults(self):
        r = AgentResult(summary="done")
        assert r.summary == "done"
        assert r.steps == 0
        assert r.success is True

    def test_fields(self):
        r = AgentResult(summary="ok", steps=5, success=False)
        assert r.steps == 5
        assert r.success is False

    def test_run_returns_agent_result(self):
        agent = Agent(api_key="k", computer_use=False)

        mock_loop = MagicMock()
        mock_loop.run.return_value = "Task completed successfully"

        with patch.object(agent, "_make_loop", return_value=mock_loop):
            result = agent.run("test instruction")

        assert isinstance(result, AgentResult)
        assert result.summary == "Task completed successfully"
        assert result.success is True
        mock_loop.run.assert_called_once_with("test instruction", app_name=None)

    def test_run_detects_failure(self):
        agent = Agent(api_key="k", computer_use=False)

        mock_loop = MagicMock()
        mock_loop.run.return_value = "Agent reached maximum steps without completing the task."

        with patch.object(agent, "_make_loop", return_value=mock_loop):
            result = agent.run("test")

        assert result.success is False

    def test_run_with_custom_app(self):
        agent = Agent(api_key="k", app="Safari")

        mock_loop = MagicMock()
        mock_loop.run.return_value = "done"

        with patch.object(agent, "_make_loop", return_value=mock_loop):
            result = agent.run("test", app="Finder")

        mock_loop.run.assert_called_once_with("test", app_name="Finder")

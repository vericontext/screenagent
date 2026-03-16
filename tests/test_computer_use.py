"""Tests for ComputerUseLoop — prompt regression, integration, helpers, stability."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from screenagent.agent.computer_use import SYSTEM_PROMPT, ComputerUseLoop
from screenagent.config import Config


# ---------------------------------------------------------------------------
# Mock blocks (same pattern as test_agent_loop.py)
# ---------------------------------------------------------------------------

@dataclass
class MockTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class MockToolUseBlock:
    type: str = "tool_use"
    id: str = "tool_1"
    name: str = "computer"
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


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def computer_use_loop():
    with (
        patch("screenagent.agent.computer_use._get_screen_size", return_value=(1440, 900)),
        patch("screenagent.agent.computer_use.ComputerUseLoop._get_frontmost_pid", return_value=100),
        patch("screenagent.agent.computer_use.anthropic.Anthropic") as mock_anthropic_cls,
        patch("screenagent.agent.computer_use.ScreenshotPerceiver"),
        patch("screenagent.agent.computer_use.AXPerceiver"),
        patch("screenagent.agent.computer_use.CGEventActor"),
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        config = Config(anthropic_api_key="test-key", max_steps=5)
        loop = ComputerUseLoop(config)
        # Patch macOS I/O on the instance
        loop._take_screenshot_b64 = MagicMock(return_value="AAAA")
        loop._get_frontmost_app = MagicMock(return_value="TestApp")
        loop._get_window_title = MagicMock(return_value="TestWindow")
        loop._get_ax_summary = MagicMock(return_value=None)
        loop._activate_app = MagicMock()
        loop._activate_pid = MagicMock()
        loop._is_app_running = MagicMock(return_value=True)
        loop._dispatch_action = MagicMock(return_value=None)
        yield loop, mock_client


def _tool_use_response(action: str, params: dict | None = None, tool_id: str = "tool_1") -> MockResponse:
    """Helper to build a tool_use response."""
    inp = {"action": action}
    if params:
        inp.update(params)
    return MockResponse(
        content=[MockToolUseBlock(id=tool_id, input=inp)],
        stop_reason="tool_use",
    )


def _end_turn_response(text: str = "Done") -> MockResponse:
    return MockResponse(
        content=[MockTextBlock(text=text)],
        stop_reason="end_turn",
    )


def _get_tool_result_content(mock_client, call_index: int = 1) -> list[dict] | str:
    """Extract tool_result content from the Nth API call's messages.

    NOTE: The mock stores a reference to the mutable messages list, so by the
    time we inspect it the list may have grown. The tool_result for step N is
    always at messages[2*call_index] (user[0], asst[1], tool_result[2], ...).
    """
    call_args = mock_client.beta.messages.create.call_args_list[call_index]
    messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
    tool_result_msg = messages[2 * call_index]
    tool_result = tool_result_msg["content"][0]
    return tool_result.get("content", "")


# ===========================================================================
# Class 1: TestSystemPromptContent — prompt regression prevention
# ===========================================================================

class TestSystemPromptContent:
    def test_contains_auto_activation(self):
        assert "automatically brings" in SYSTEM_PROMPT

    def test_contains_truncation_warning(self):
        assert "may be truncated" in SYSTEM_PROMPT

    def test_contains_accessibility_unavailable(self):
        assert "accessibility info is unavailable" in SYSTEM_PROMPT

    def test_multi_window_no_old_phrasing(self):
        """Multi-Window Recovery section starts with 'The system automatically'."""
        idx = SYSTEM_PROMPT.index("## Multi-Window Recovery")
        section = SYSTEM_PROMPT[idx:]
        first_bullet = section.split("\n")[1].strip()
        assert first_bullet.startswith("- The system automatically")

    def test_length_under_threshold(self):
        assert len(SYSTEM_PROMPT) < 4000


# ===========================================================================
# Class 2: TestComputerUseLoopIntegration — arun flow verification
# ===========================================================================

class TestComputerUseLoopIntegration:
    def test_end_turn_returns_text(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        mock_client.beta.messages.create.return_value = _end_turn_response("Task complete")
        result = asyncio.run(loop.arun("do something", app_name="Safari"))
        assert result == "Task complete"

    def test_max_steps_reached(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        loop._config = Config(anthropic_api_key="test-key", max_steps=1)
        mock_client.beta.messages.create.return_value = _tool_use_response("screenshot")
        result = asyncio.run(loop.arun("do something"))
        assert "maximum steps" in result

    def test_activate_app_called_for_gui_action(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("left_click", {"coordinate": [100, 200]}),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("click", app_name="Safari"))
        loop._activate_app.assert_any_call("Safari")

    def test_activate_app_not_called_for_screenshot(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("screenshot"),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("take screenshot", app_name="Safari"))
        # _activate_app is called once at the start of arun for app_name, but NOT for the screenshot action
        # We check that calls after initial activation don't include screenshot-triggered calls
        # Initial call: arun calls _activate_app("Safari") once at the top
        # The screenshot action should NOT trigger another _activate_app call
        assert loop._activate_app.call_count == 1  # only the initial activation

    def test_activate_app_not_called_for_wait(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("wait", {"duration": 1}),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("wait", app_name="Safari"))
        assert loop._activate_app.call_count == 1  # only initial

    def test_activate_pid_fallback(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        loop._target_app_pid = 999
        loop._target_app_name = None
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("left_click", {"coordinate": [100, 200]}),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("click"))  # no app_name
        loop._activate_pid.assert_called_with(999)

    def test_activate_target_app_name(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        loop._target_app_name = "Notes"
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("left_click", {"coordinate": [100, 200]}),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("click"))  # no app_name
        loop._activate_app.assert_called_with("Notes")

    def test_ax_tree_in_tool_result(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        loop._get_ax_summary = MagicMock(return_value="AXButton 'OK'")
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("left_click", {"coordinate": [100, 200]}),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("click", app_name="Safari"))
        content = _get_tool_result_content(mock_client, call_index=1)
        texts = [p["text"] for p in content if p.get("type") == "text"]
        joined = "\n".join(texts)
        assert "UI Elements:\nAXButton 'OK'" in joined

    def test_ax_tree_absent_no_ui_elements(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        loop._get_ax_summary = MagicMock(return_value=None)
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("left_click", {"coordinate": [100, 200]}),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("click", app_name="Safari"))
        content = _get_tool_result_content(mock_client, call_index=1)
        texts = [p["text"] for p in content if p.get("type") == "text"]
        joined = "\n".join(texts)
        assert "UI Elements:" not in joined

    def test_repetition_warning(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("left_click", {"coordinate": [100, 200]}, tool_id="t1"),
            _tool_use_response("left_click", {"coordinate": [100, 200]}, tool_id="t2"),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("click", app_name="Safari"))
        # Second click should trigger WARNING
        content = _get_tool_result_content(mock_client, call_index=2)
        texts = [p["text"] for p in content if p.get("type") == "text"]
        joined = "\n".join(texts)
        assert "WARNING" in joined

    def test_no_visible_change_note(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        # First action sets prev_app/prev_window, second sees same → note
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("left_click", {"coordinate": [100, 200]}, tool_id="t1"),
            _tool_use_response("left_click", {"coordinate": [300, 400]}, tool_id="t2"),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("click", app_name="Safari"))
        content = _get_tool_result_content(mock_client, call_index=2)
        texts = [p["text"] for p in content if p.get("type") == "text"]
        joined = "\n".join(texts)
        assert "No visible window change" in joined

    def test_app_change_note(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        # After first action, app changes
        loop._get_frontmost_app = MagicMock(side_effect=["Safari", "Finder"])
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("left_click", {"coordinate": [100, 200]}, tool_id="t1"),
            _tool_use_response("left_click", {"coordinate": [300, 400]}, tool_id="t2"),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("click", app_name="Safari"))
        content = _get_tool_result_content(mock_client, call_index=2)
        texts = [p["text"] for p in content if p.get("type") == "text"]
        joined = "\n".join(texts)
        assert "App changed from" in joined

    def test_dispatch_error_returns_error_result(self, computer_use_loop):
        loop, mock_client = computer_use_loop
        loop._dispatch_action = MagicMock(return_value="Unknown action: foobar")
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("foobar"),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("do something", app_name="Safari"))
        # Tool result for step 0 is at messages[2]
        call_args = mock_client.beta.messages.create.call_args_list[1]
        messages = call_args[1]["messages"]
        tool_result_msg = messages[2]  # user msg with tool_results
        tool_result = tool_result_msg["content"][0]
        assert tool_result.get("is_error") is True


# ===========================================================================
# Class 3: TestHelperMethods — unit tests
# ===========================================================================

class TestHelperMethods:
    def _make_loop(self):
        """Create a minimal ComputerUseLoop for testing helpers."""
        with (
            patch("screenagent.agent.computer_use._get_screen_size", return_value=(1440, 900)),
            patch("screenagent.agent.computer_use.ComputerUseLoop._get_frontmost_pid", return_value=100),
            patch("screenagent.agent.computer_use.anthropic.Anthropic"),
            patch("screenagent.agent.computer_use.ScreenshotPerceiver"),
            patch("screenagent.agent.computer_use.AXPerceiver"),
            patch("screenagent.agent.computer_use.CGEventActor"),
        ):
            config = Config(anthropic_api_key="test-key", max_steps=5)
            return ComputerUseLoop(config)

    def test_action_key_fuzzy_match(self):
        loop = self._make_loop()
        k1 = loop._action_key("left_click", {"coordinate": [1130, 633]})
        k2 = loop._action_key("left_click", {"coordinate": [1130, 635]})
        assert k1 == k2

    def test_action_key_distant_coords_differ(self):
        loop = self._make_loop()
        k1 = loop._action_key("left_click", {"coordinate": [100, 100]})
        k2 = loop._action_key("left_click", {"coordinate": [500, 500]})
        assert k1 != k2

    def test_action_key_text(self):
        loop = self._make_loop()
        k = loop._action_key("type", {"text": "hello"})
        assert k == "type:hello"

    def test_trim_no_change_under_20(self):
        loop = self._make_loop()
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(18)]
        result = loop._trim_with_summary(messages)
        assert len(result) == 18

    def test_trim_over_20(self):
        loop = self._make_loop()
        loop._action_log = [f"action {i}" for i in range(12)]
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(24)]
        result = loop._trim_with_summary(messages)
        assert len(result) == 19
        assert result[0] == messages[0]  # first message preserved
        assert "summarized" in result[1]["content"][0]["text"].lower()


# ===========================================================================
# Class 4: TestPromptStability — token estimation
# ===========================================================================

class TestPromptStability:
    def test_token_estimate_under_1000(self):
        assert len(SYSTEM_PROMPT) / 4 < 1000

    def test_no_mode_switch_in_calculator(self):
        assert "NEVER switch calculator modes" in SYSTEM_PROMPT

    def test_prompt_contains_already_active_hint(self):
        assert "already active" in SYSTEM_PROMPT


# ===========================================================================
# Class 5: TestAppRunningGuard — _is_app_running & activation guards
# ===========================================================================

class TestAppRunningGuard:
    def _make_loop(self):
        """Create a minimal ComputerUseLoop for testing."""
        with (
            patch("screenagent.agent.computer_use._get_screen_size", return_value=(1440, 900)),
            patch("screenagent.agent.computer_use.ComputerUseLoop._get_frontmost_pid", return_value=100),
            patch("screenagent.agent.computer_use.anthropic.Anthropic"),
            patch("screenagent.agent.computer_use.ScreenshotPerceiver"),
            patch("screenagent.agent.computer_use.AXPerceiver"),
            patch("screenagent.agent.computer_use.CGEventActor"),
        ):
            config = Config(anthropic_api_key="test-key", max_steps=5)
            return ComputerUseLoop(config)

    @patch("screenagent.agent.computer_use.ComputerUseLoop._is_app_running", return_value=False)
    @patch("screenagent.agent.computer_use.subprocess.Popen")
    def test_activate_app_skips_when_not_running(self, mock_popen, mock_running):
        """_activate_app should NOT call subprocess when app is not running."""
        ComputerUseLoop._activate_app("Calculator")
        mock_popen.assert_not_called()

    @patch("screenagent.agent.computer_use.ComputerUseLoop._is_app_running", return_value=True)
    @patch("screenagent.agent.computer_use.subprocess.Popen")
    def test_activate_app_calls_when_running(self, mock_popen, mock_running):
        """_activate_app should call subprocess when app is running."""
        ComputerUseLoop._activate_app("Calculator")
        mock_popen.assert_called_once()

    def test_activation_skipped_during_spotlight(self, computer_use_loop):
        """activate should not be called when _spotlight_active is True."""
        loop, mock_client = computer_use_loop
        loop._spotlight_active = True
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("type", {"text": "Calculator"}),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("open calculator", app_name="Calculator"))
        # Only the initial activation in arun (before the loop), not during the tool action
        assert loop._activate_app.call_count == 1


# ===========================================================================
# Class 6: TestPromptCaching — cache_control on recent user messages
# ===========================================================================

class TestPromptCaching:
    def test_cache_control_added_to_recent_user_messages(self, computer_use_loop):
        """API call should include cache_control on recent user message content blocks."""
        loop, mock_client = computer_use_loop
        mock_client.beta.messages.create.side_effect = [
            _tool_use_response("screenshot"),
            _end_turn_response(),
        ]
        asyncio.run(loop.arun("do something"))
        # Check the second API call's messages for cache_control
        call_args = mock_client.beta.messages.create.call_args_list[1]
        messages = call_args[1]["messages"]
        # Find user messages with list content
        cached = []
        for msg in messages:
            if msg["role"] == "user" and isinstance(msg["content"], list):
                last_block = msg["content"][-1]
                if isinstance(last_block, dict) and "cache_control" in last_block:
                    cached.append(msg)
        assert len(cached) >= 1

    def test_prompt_caching_beta_flag(self, computer_use_loop):
        """API call should include prompt-caching beta flag."""
        loop, mock_client = computer_use_loop
        mock_client.beta.messages.create.return_value = _end_turn_response()
        asyncio.run(loop.arun("do something"))
        call_args = mock_client.beta.messages.create.call_args_list[0]
        betas = call_args[1]["betas"]
        assert "prompt-caching-2024-07-31" in betas


# ===========================================================================
# Class 7: TestSystemPromptLaunchVerification — screenshot verification hints
# ===========================================================================

class TestSystemPromptLaunchVerification:
    def test_screenshot_verify_after_launch(self):
        assert "take a screenshot to verify" in SYSTEM_PROMPT.lower()

    def test_wait_and_screenshot_again(self):
        assert "wait action" in SYSTEM_PROMPT.lower()

    def test_confirm_app_launched(self):
        assert "confirm the app has launched" in SYSTEM_PROMPT.lower()

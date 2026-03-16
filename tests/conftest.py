"""Shared fixtures for tests."""

from __future__ import annotations

import pytest

from screenagent.types import Rect, UIElement, ScreenState
from screenagent.config import Config


@pytest.fixture
def sample_config():
    return Config(
        anthropic_api_key="test-key",
        cdp_port=9222,
        max_steps=5,
        model="claude-sonnet-4-6",
    )


@pytest.fixture
def sample_ui_tree():
    return UIElement(
        role="AXApplication",
        title="Google Chrome",
        children=[
            UIElement(
                role="AXWindow",
                title="New Tab",
                rect=Rect(0, 0, 1440, 900),
                children=[
                    UIElement(
                        role="AXTextField",
                        title="Address and search bar",
                        value="https://google.com",
                        rect=Rect(200, 50, 800, 30),
                    ),
                    UIElement(
                        role="AXWebArea",
                        title="Google",
                        rect=Rect(0, 80, 1440, 820),
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def sample_screen_state(sample_ui_tree):
    return ScreenState(
        ui_tree=sample_ui_tree,
        url="https://google.com",
        app_name="Google Chrome",
    )

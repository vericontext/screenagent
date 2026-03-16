"""Tests for shortcut functions."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from screenagent import shortcuts


class TestScreenshot:
    def test_returns_bytes(self):
        mock_perceiver = MagicMock()
        mock_perceiver.screenshot.return_value = b"\x89PNG"

        with patch("screenagent.perception.screenshot.ScreenshotPerceiver", return_value=mock_perceiver):
            result = shortcuts.screenshot()

        assert result == b"\x89PNG"
        mock_perceiver.screenshot.assert_called_once_with(None)

    def test_with_region(self):
        from screenagent.types import Rect
        region = Rect(x=0, y=0, width=100, height=100)

        mock_perceiver = MagicMock()
        mock_perceiver.screenshot.return_value = b"img"

        with patch("screenagent.perception.screenshot.ScreenshotPerceiver", return_value=mock_perceiver):
            shortcuts.screenshot(region)

        mock_perceiver.screenshot.assert_called_once_with(region)


class TestClick:
    def test_delegates_to_actor(self):
        mock_actor = MagicMock()
        with patch("screenagent.action.cgevent.CGEventActor", return_value=mock_actor):
            shortcuts.click(100.0, 200.0)
        mock_actor.click.assert_called_once_with(100.0, 200.0)


class TestDoubleClick:
    def test_delegates_to_actor(self):
        mock_actor = MagicMock()
        with patch("screenagent.action.cgevent.CGEventActor", return_value=mock_actor):
            shortcuts.double_click(100.0, 200.0)
        mock_actor.double_click.assert_called_once_with(100.0, 200.0)


class TestTypeText:
    def test_delegates_to_actor(self):
        mock_actor = MagicMock()
        with patch("screenagent.action.cgevent.CGEventActor", return_value=mock_actor):
            shortcuts.type_text("hello")
        mock_actor.type_text.assert_called_once_with("hello")


class TestKeyPress:
    def test_without_modifiers(self):
        mock_actor = MagicMock()
        with patch("screenagent.action.cgevent.CGEventActor", return_value=mock_actor):
            shortcuts.key_press("return")
        mock_actor.key_press.assert_called_once_with("return", None)

    def test_with_modifiers(self):
        mock_actor = MagicMock()
        with patch("screenagent.action.cgevent.CGEventActor", return_value=mock_actor):
            shortcuts.key_press("l", ["command"])
        mock_actor.key_press.assert_called_once_with("l", ["command"])


class TestScroll:
    def test_delegates_to_actor(self):
        mock_actor = MagicMock()
        with patch("screenagent.action.cgevent.CGEventActor", return_value=mock_actor):
            shortcuts.scroll(640.0, 400.0, 0.0, -100.0)
        mock_actor.scroll.assert_called_once_with(640.0, 400.0, 0.0, -100.0)


class TestGetUiTree:
    def test_returns_ui_element(self):
        from screenagent.types import UIElement
        mock_tree = UIElement(role="AXApplication", title="Finder")

        mock_perceiver = MagicMock()
        mock_perceiver.get_ui_tree.return_value = mock_tree

        with patch("screenagent.perception.ax.AXPerceiver", return_value=mock_perceiver):
            result = shortcuts.get_ui_tree("Finder")

        assert result is mock_tree
        mock_perceiver.get_ui_tree.assert_called_once_with("Finder")

    def test_returns_none_when_not_found(self):
        mock_perceiver = MagicMock()
        mock_perceiver.get_ui_tree.return_value = None

        with patch("screenagent.perception.ax.AXPerceiver", return_value=mock_perceiver):
            result = shortcuts.get_ui_tree("NonExistent")

        assert result is None

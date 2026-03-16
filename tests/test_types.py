"""Tests for core data types."""

from screenagent.types import Rect, UIElement, ScreenState, ToolResult


class TestRect:
    def test_center(self):
        r = Rect(100, 200, 50, 30)
        assert r.center == (125.0, 215.0)

    def test_contains(self):
        r = Rect(10, 20, 100, 50)
        assert r.contains(50, 40)
        assert r.contains(10, 20)  # top-left edge
        assert r.contains(110, 70)  # bottom-right edge
        assert not r.contains(5, 40)
        assert not r.contains(50, 80)

    def test_frozen(self):
        r = Rect(0, 0, 10, 10)
        import pytest
        with pytest.raises(AttributeError):
            r.x = 5  # type: ignore


class TestUIElement:
    def test_to_text_simple(self):
        elem = UIElement(role="AXButton", title="OK")
        assert elem.to_text() == 'AXButton "OK"'

    def test_to_text_with_rect(self):
        elem = UIElement(role="AXButton", title="OK", rect=Rect(10, 20, 80, 30))
        text = elem.to_text()
        assert "AXButton" in text
        assert "(10,20 80x30)" in text

    def test_to_text_nested(self):
        parent = UIElement(
            role="AXWindow",
            title="Main",
            children=[
                UIElement(role="AXButton", title="Save"),
                UIElement(role="AXButton", title="Cancel"),
            ],
        )
        text = parent.to_text()
        lines = text.split("\n")
        assert len(lines) == 3
        assert lines[0].startswith("AXWindow")
        assert lines[1].startswith("  AXButton")
        assert lines[2].startswith("  AXButton")

    def test_to_text_value(self):
        elem = UIElement(role="AXTextField", value="hello")
        assert "value='hello'" in elem.to_text()


class TestScreenState:
    def test_to_text(self):
        state = ScreenState(
            app_name="Finder",
            url="https://example.com",
            ui_tree=UIElement(role="AXApplication", title="Finder"),
        )
        text = state.to_text()
        assert "App: Finder" in text
        assert "URL: https://example.com" in text
        assert "UI Tree:" in text


class TestToolResult:
    def test_defaults(self):
        r = ToolResult()
        assert r.output == ""
        assert r.error == ""
        assert r.screenshot_png is None
        assert r.done is False

    def test_done(self):
        r = ToolResult(output="Task complete", done=True)
        assert r.done

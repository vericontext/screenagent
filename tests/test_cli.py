"""Tests for the CLI entry point."""

from __future__ import annotations

import json

import pytest

from screenagent.cli import build_parser, main, _has_control_chars


def run_cli(*argv: str) -> int:
    """Run main() and return exit code without raising SystemExit."""
    try:
        main(list(argv))
    except SystemExit as exc:
        return exc.code
    return 0


class TestControlCharDetection:
    def test_clean_string(self):
        assert not _has_control_chars("hello world")

    def test_newline_tab_allowed(self):
        # \n, \r, \t are common whitespace — not flagged
        assert not _has_control_chars("line1\nline2")
        assert not _has_control_chars("col1\tcol2")

    def test_null_byte(self):
        assert _has_control_chars("hello\x00world")

    def test_escape(self):
        assert _has_control_chars("hello\x1bworld")


class TestParser:
    def test_schema_command(self):
        parser = build_parser()
        args = parser.parse_args(["schema"])
        assert args.command == "schema"

    def test_run_command(self):
        parser = build_parser()
        args = parser.parse_args(["run", "do something", "--app", "Finder", "--dry-run"])
        assert args.command == "run"
        assert args.instruction == "do something"
        assert args.app == "Finder"
        assert args.dry_run is True

    def test_click_command(self):
        parser = build_parser()
        args = parser.parse_args(["click", "100", "200"])
        assert args.command == "click"
        assert args.x == "100"
        assert args.y == "200"

    def test_type_command(self):
        parser = build_parser()
        args = parser.parse_args(["type", "hello world"])
        assert args.command == "type"
        assert args.text == "hello world"

    def test_key_command_with_modifiers(self):
        parser = build_parser()
        args = parser.parse_args(["key", "return", "--modifiers", "command"])
        assert args.command == "key"
        assert args.key == "return"
        assert args.modifiers == ["command"]

    def test_ax_tree_command(self):
        parser = build_parser()
        args = parser.parse_args(["ax-tree", "Google Chrome", "--fields", "role,title,rect"])
        assert args.command == "ax-tree"
        assert args.app_name == "Google Chrome"
        assert args.fields == "role,title,rect"

    def test_screenshot_command(self):
        parser = build_parser()
        args = parser.parse_args(["screenshot", "--file", "/tmp/test.png"])
        assert args.command == "screenshot"
        assert args.file == "/tmp/test.png"

    def test_output_json(self):
        parser = build_parser()
        args = parser.parse_args(["--output", "json", "schema"])
        assert args.output == "json"

    def test_default_output_text(self):
        parser = build_parser()
        args = parser.parse_args(["schema"])
        assert args.output == "text"


class TestSchemaCommand:
    def test_schema_outputs_json(self, capsys):
        assert run_cli("schema") == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "tools" in data
        tool_names = {t["name"] for t in data["tools"]}
        assert "click" in tool_names
        assert "screenshot" in tool_names
        assert "done" in tool_names

    def test_schema_json_mode(self, capsys):
        assert run_cli("--output", "json", "schema") == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "tools" in data


class TestRunDryRun:
    def test_dry_run_text(self, capsys, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        assert run_cli("run", "do something", "--dry-run") == 0
        captured = capsys.readouterr()
        assert "api_key_set: True" in captured.out

    def test_dry_run_json(self, capsys, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        assert run_cli("--output", "json", "run", "do something", "--dry-run") == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is True
        assert data["config"]["api_key_set"] is True

    def test_dry_run_no_key(self, capsys, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert run_cli("--output", "json", "run", "do something", "--dry-run") == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is False

    def test_run_validation_error_control_chars(self, capsys):
        code = run_cli("--output", "json", "run", "bad\x00input")
        assert code == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["code"] == "validation_error"


class TestClickValidation:
    def test_non_numeric_coords(self, capsys):
        code = run_cli("--output", "json", "click", "abc", "200")
        assert code == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["code"] == "validation_error"


class TestCheckCommand:
    def test_check_parser(self):
        parser = build_parser()
        args = parser.parse_args(["check", "--cdp-port", "9333"])
        assert args.command == "check"
        assert args.cdp_port == 9333

    def test_check_default_port(self):
        parser = build_parser()
        args = parser.parse_args(["check"])
        assert args.cdp_port == 9222

    def test_check_json_output_structure(self, capsys, monkeypatch):
        """Check command returns JSON with expected structure (CDP not running)."""
        # Patch urlopen to simulate no CDP
        import screenagent.cli
        monkeypatch.setattr(
            "screenagent.cli.urlopen",
            lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("no cdp")),
        )
        code = run_cli("--output", "json", "check")
        assert code == 1  # Fails because CDP isn't reachable
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "ok" in data
        assert "checks" in data
        assert data["ok"] is False
        assert data["checks"]["cdp_port"] == 9222

    def test_check_text_output(self, capsys, monkeypatch):
        """Check command produces text output."""
        import screenagent.cli
        monkeypatch.setattr(
            "screenagent.cli.urlopen",
            lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("no cdp")),
        )
        code = run_cli("check")
        assert code == 1
        captured = capsys.readouterr()
        assert "CDP check: FAIL" in captured.out


class TestNoCommand:
    def test_no_subcommand_exits_2(self):
        assert run_cli() == 2

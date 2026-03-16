"""Agent-friendly CLI entry point for screenagent.

Subcommands:
    run          Execute an agent loop with a natural-language instruction
    screenshot   Capture a screenshot of the current screen
    ax-tree      Dump the accessibility tree of an application
    click        Click at screen coordinates
    type         Type text via the keyboard
    key          Press a key with optional modifiers
    schema       Dump tool schemas as JSON for runtime introspection

All commands support --output json|text for structured output.
Exit codes: 0 = success, 1 = runtime error, 2 = validation error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_control_chars(s: str) -> bool:
    """Return True if string contains control characters (except common whitespace)."""
    return bool(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", s))


def _error(msg: str, *, output: str, code: str = "error", exit_code: int = 1) -> int:
    """Print an error and return the exit code."""
    if output == "json":
        json.dump({"error": msg, "code": code}, sys.stdout)
        sys.stdout.write("\n")
    else:
        print(f"Error: {msg}", file=sys.stderr)
    return exit_code


def _validation_error(msg: str, *, output: str) -> int:
    return _error(msg, output=output, code="validation_error", exit_code=2)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    instruction: str = args.instruction
    if _has_control_chars(instruction):
        return _validation_error("Instruction contains control characters", output=args.output)

    from screenagent.config import Config

    config = Config.from_env()
    # CLI overrides
    if args.cdp_port is not None:
        config.cdp_port = args.cdp_port
    if args.max_steps is not None:
        config.max_steps = args.max_steps
    if args.model is not None:
        config.model = args.model

    if args.dry_run:
        checks: dict[str, object] = {
            "api_key_set": bool(config.anthropic_api_key),
            "cdp_port": config.cdp_port,
            "max_steps": config.max_steps,
            "model": config.model,
            "app": args.app,
        }
        if args.output == "json":
            json.dump({"ok": checks["api_key_set"], "config": checks}, sys.stdout)
            sys.stdout.write("\n")
        else:
            for k, v in checks.items():
                print(f"{k}: {v}")
        return 0

    if not config.anthropic_api_key:
        return _error("ANTHROPIC_API_KEY is not set", output=args.output, code="missing_api_key")

    # Stream step logs to stderr so stdout contains only the result
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # CLI flags override config default
    use_computer = config.computer_use
    if args.computer_use:
        use_computer = True
    elif args.no_computer_use:
        use_computer = False

    if use_computer:
        from screenagent.agent.computer_use import ComputerUseLoop
        loop = ComputerUseLoop(config=config)
    else:
        from screenagent.agent.loop import AgentLoop
        loop = AgentLoop(config=config)

    try:
        result = loop.run(instruction, app_name=args.app)
    except Exception as exc:
        return _error(str(exc), output=args.output)

    if args.output == "json":
        json.dump({"result": result}, sys.stdout)
        sys.stdout.write("\n")
    else:
        print(result)
    return 0


def cmd_screenshot(args: argparse.Namespace) -> int:
    from screenagent.perception.screenshot import ScreenshotPerceiver

    perceiver = ScreenshotPerceiver()
    try:
        png_bytes = perceiver.screenshot()
    except Exception as exc:
        return _error(str(exc), output=args.output)

    # Write to file
    out_path = args.file
    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".png", prefix="screenagent_")
        import os
        os.close(fd)

    Path(out_path).write_bytes(png_bytes)

    if args.output == "json":
        json.dump({"path": out_path, "bytes": len(png_bytes)}, sys.stdout)
        sys.stdout.write("\n")
    else:
        print(out_path)
    return 0


def cmd_ax_tree(args: argparse.Namespace) -> int:
    app_name: str = args.app_name
    if _has_control_chars(app_name):
        return _validation_error("App name contains control characters", output=args.output)

    from screenagent.perception.ax import AXPerceiver

    perceiver = AXPerceiver()
    try:
        tree = perceiver.get_ui_tree(app_name)
    except PermissionError as exc:
        return _error(str(exc), output=args.output, code="permission_error")
    except Exception as exc:
        return _error(str(exc), output=args.output)

    if tree is None:
        return _error(f"Application {app_name!r} not found", output=args.output, code="app_not_found")

    if args.output == "json":
        def _elem_to_dict(elem, fields: list[str] | None, depth: int = 0, max_depth: int = 50) -> dict:
            if depth > max_depth:
                return {"role": elem.role, "truncated": True}
            d: dict[str, object] = {}
            all_fields = fields is None
            if all_fields or "role" in fields:
                d["role"] = elem.role
            if all_fields or "title" in fields:
                d["title"] = elem.title
            if all_fields or "value" in fields:
                d["value"] = elem.value
            if all_fields or "rect" in fields:
                d["rect"] = (
                    {"x": elem.rect.x, "y": elem.rect.y, "width": elem.rect.width, "height": elem.rect.height}
                    if elem.rect else None
                )
            if elem.children and (all_fields or "children" in fields):
                d["children"] = [_elem_to_dict(c, fields, depth + 1, max_depth) for c in elem.children]
            return d

        fields = [f.strip() for f in args.fields.split(",")] if args.fields else None
        json.dump(_elem_to_dict(tree, fields), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(tree.to_text())
    return 0


def cmd_click(args: argparse.Namespace) -> int:
    try:
        x, y = float(args.x), float(args.y)
    except ValueError:
        return _validation_error("Coordinates must be numeric", output=args.output)

    from screenagent.action.cgevent import CGEventActor

    actor = CGEventActor()
    try:
        actor.click(x, y)
    except Exception as exc:
        return _error(str(exc), output=args.output)

    if args.output == "json":
        json.dump({"clicked": {"x": x, "y": y}}, sys.stdout)
        sys.stdout.write("\n")
    else:
        print(f"Clicked ({x}, {y})")
    return 0


def cmd_type(args: argparse.Namespace) -> int:
    text: str = args.text
    if _has_control_chars(text):
        return _validation_error("Text contains control characters", output=args.output)

    from screenagent.action.cgevent import CGEventActor

    actor = CGEventActor()
    try:
        actor.type_text(text)
    except Exception as exc:
        return _error(str(exc), output=args.output)

    if args.output == "json":
        json.dump({"typed": text, "length": len(text)}, sys.stdout)
        sys.stdout.write("\n")
    else:
        print(f"Typed {len(text)} character(s)")
    return 0


def cmd_key(args: argparse.Namespace) -> int:
    key: str = args.key
    modifiers: list[str] | None = args.modifiers

    from screenagent.action.cgevent import CGEventActor

    actor = CGEventActor()
    try:
        actor.key_press(key, modifiers)
    except ValueError as exc:
        return _validation_error(str(exc), output=args.output)
    except Exception as exc:
        return _error(str(exc), output=args.output)

    result = {"key": key}
    if modifiers:
        result["modifiers"] = modifiers

    if args.output == "json":
        json.dump({"pressed": result}, sys.stdout)
        sys.stdout.write("\n")
    else:
        mod_str = "+".join(modifiers) + "+" if modifiers else ""
        print(f"Pressed {mod_str}{key}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Diagnose CDP connectivity."""
    port = args.cdp_port
    checks: dict[str, object] = {
        "cdp_port": port,
        "http_reachable": False,
        "page_targets": 0,
        "chrome_running": False,
        "chrome_debug_flags": [],
    }

    # 1. HTTP check
    try:
        resp = urlopen(f"http://localhost:{port}/json/version", timeout=5).read()
        version_info = json.loads(resp)
        checks["http_reachable"] = True
        checks["browser_version"] = version_info.get("Browser", "unknown")
    except Exception:
        pass

    # 2. Page targets
    if checks["http_reachable"]:
        try:
            resp = urlopen(f"http://localhost:{port}/json", timeout=5).read()
            targets = json.loads(resp)
            checks["page_targets"] = sum(1 for t in targets if t.get("type") == "page")
        except Exception:
            pass

    # 3. Chrome process check
    try:
        result = subprocess.run(
            ["pgrep", "-af", "Google Chrome"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            checks["chrome_running"] = True
            lines = result.stdout.strip().splitlines()
            for line in lines:
                if f"--remote-debugging-port={port}" in line:
                    checks["chrome_debug_flags"].append(f"--remote-debugging-port={port}")
                if "--user-data-dir=" in line:
                    import re as _re
                    m = _re.search(r"--user-data-dir=(\S+)", line)
                    if m:
                        checks["chrome_debug_flags"].append(f"--user-data-dir={m.group(1)}")
    except Exception:
        pass

    ok = checks["http_reachable"] and checks["page_targets"] > 0

    if args.output == "json":
        json.dump({"ok": ok, "checks": checks}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        status = "OK" if ok else "FAIL"
        print(f"CDP check: {status}")
        print(f"  Port:           {port}")
        print(f"  HTTP reachable: {checks['http_reachable']}")
        print(f"  Page targets:   {checks['page_targets']}")
        print(f"  Chrome running: {checks['chrome_running']}")
        if checks["chrome_debug_flags"]:
            print(f"  Debug flags:    {', '.join(checks['chrome_debug_flags'])}")
        if not ok:
            print()
            print("Tip: Launch Chrome with:")
            print(f"  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
                  f"--remote-debugging-port={port} --user-data-dir=/tmp/chrome-debug-profile")
    return 0 if ok else 1


def cmd_schema(args: argparse.Namespace) -> int:
    from screenagent.agent.tools import TOOLS

    if args.output == "json" or args.output == "text":
        # Schema is always JSON — it's the whole point
        json.dump({"tools": TOOLS}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="screenagent",
        description="macOS GUI automation — agent-friendly CLI",
    )
    parser.add_argument(
        "--output", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )

    sub = parser.add_subparsers(dest="command")

    # --- run ---
    p_run = sub.add_parser("run", help="Execute an agent loop")
    p_run.add_argument("instruction", help="Natural-language task instruction")
    p_run.add_argument("--app", default=None, help="Target application (default: None — agent decides)")
    p_run.add_argument("--cdp-port", type=int, default=None, help="Chrome DevTools Protocol port")
    p_run.add_argument("--max-steps", type=int, default=None, help="Maximum agent steps")
    p_run.add_argument("--model", default=None, help="Claude model to use")
    p_run.add_argument("--dry-run", action="store_true", help="Validate config without executing")
    p_run.add_argument("--computer-use", action="store_true", help="Force computer-use mode (default: on)")
    p_run.add_argument("--no-computer-use", action="store_true", help="Disable computer-use, use legacy tool-use mode")

    # --- screenshot ---
    p_ss = sub.add_parser("screenshot", help="Capture a screenshot")
    p_ss.add_argument("--file", default=None, help="Output file path (default: temp file)")

    # --- ax-tree ---
    p_ax = sub.add_parser("ax-tree", help="Dump accessibility tree")
    p_ax.add_argument("app_name", help="Application name (e.g. 'Google Chrome')")
    p_ax.add_argument("--fields", default=None, help="Comma-separated fields to include (role,title,value,rect,children)")

    # --- click ---
    p_click = sub.add_parser("click", help="Click at screen coordinates")
    p_click.add_argument("x", help="X coordinate")
    p_click.add_argument("y", help="Y coordinate")

    # --- type ---
    p_type = sub.add_parser("type", help="Type text via keyboard")
    p_type.add_argument("text", help="Text to type")

    # --- key ---
    p_key = sub.add_parser("key", help="Press a key")
    p_key.add_argument("key", help="Key name (e.g. return, tab, a)")
    p_key.add_argument("--modifiers", nargs="*", help="Modifier keys (command, shift, option, control)")

    # --- check ---
    p_check = sub.add_parser("check", help="Diagnose CDP connectivity")
    p_check.add_argument("--cdp-port", type=int, default=9222, help="Chrome DevTools Protocol port (default: 9222)")

    # --- schema ---
    sub.add_parser("schema", help="Dump tool schemas as JSON")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(2)

    dispatch = {
        "run": cmd_run,
        "screenshot": cmd_screenshot,
        "ax-tree": cmd_ax_tree,
        "click": cmd_click,
        "type": cmd_type,
        "key": cmd_key,
        "check": cmd_check,
        "schema": cmd_schema,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(2)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()

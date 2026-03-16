"""AXPerceiver — macOS Accessibility API tree reader using pyobjc."""

from __future__ import annotations

import logging

from screenagent.types import Rect, UIElement
from screenagent.perception.screenshot import ScreenshotPerceiver

logger = logging.getLogger(__name__)

# Lazy imports to allow the module to be imported without pyobjc installed
_ax_imported = False
_AXIsProcessTrusted = None
_AXUIElementCreateApplication = None
_NSWorkspace = None


def _ensure_ax_imports():
    global _ax_imported, _AXIsProcessTrusted, _AXUIElementCreateApplication, _NSWorkspace
    if _ax_imported:
        return
    from ApplicationServices import AXIsProcessTrusted, AXUIElementCreateApplication
    from AppKit import NSWorkspace
    _AXIsProcessTrusted = AXIsProcessTrusted
    _AXUIElementCreateApplication = AXUIElementCreateApplication
    _NSWorkspace = NSWorkspace
    _ax_imported = True


def _get_ax_attr(element, attr: str):
    """Safely read an AX attribute, returning None on error."""
    try:
        from ApplicationServices import AXUIElementCopyAttributeValue
        import CoreFoundation
        err, value = AXUIElementCopyAttributeValue(element, attr, None)
        if err == 0:
            return value
    except Exception:
        pass
    return None


class AXPerceiver:
    def __init__(self):
        self._screenshot = ScreenshotPerceiver()

    def _check_trusted(self) -> None:
        _ensure_ax_imports()
        if not _AXIsProcessTrusted():
            raise PermissionError(
                "Accessibility permission not granted. "
                "Go to System Settings → Privacy & Security → Accessibility "
                "and add your terminal/IDE."
            )

    def _find_app_pid(self, app_name: str) -> int | None:
        _ensure_ax_imports()
        workspace = _NSWorkspace.sharedWorkspace()
        for app in workspace.runningApplications():
            if app.localizedName() == app_name:
                return app.processIdentifier()
        return None

    def _read_element(self, element, depth: int = 0, max_depth: int = 10) -> UIElement | None:
        if depth > max_depth:
            return None

        role = _get_ax_attr(element, "AXRole") or "Unknown"
        title = _get_ax_attr(element, "AXTitle") or ""
        value = _get_ax_attr(element, "AXValue")
        value_str = str(value) if value is not None else ""

        # Truncate long values
        if len(value_str) > 200:
            value_str = value_str[:200] + "..."

        rect = None
        pos = _get_ax_attr(element, "AXPosition")
        size = _get_ax_attr(element, "AXSize")
        if pos is not None and size is not None:
            try:
                rect = Rect(
                    x=float(pos.x), y=float(pos.y),
                    width=float(size.width), height=float(size.height),
                )
            except (AttributeError, TypeError):
                pass

        children_raw = _get_ax_attr(element, "AXChildren") or []
        children: list[UIElement] = []
        for child in children_raw:
            child_elem = self._read_element(child, depth + 1, max_depth)
            if child_elem is not None:
                children.append(child_elem)

        return UIElement(
            role=str(role),
            title=str(title),
            value=value_str,
            rect=rect,
            children=children,
        )

    def get_ui_tree(self, app_name: str) -> UIElement | None:
        self._check_trusted()
        pid = self._find_app_pid(app_name)
        if pid is None:
            logger.warning("App %r not found in running applications", app_name)
            return None

        _ensure_ax_imports()
        app_ref = _AXUIElementCreateApplication(pid)
        return self._read_element(app_ref)

    def screenshot(self, region: Rect | None = None) -> bytes:
        return self._screenshot.screenshot(region)

    def get_text_content(self, element_id: str) -> str:
        return ""

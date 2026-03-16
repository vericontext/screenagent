"""Tests for AXPerceiver._find_app_pid — case-insensitive 3-tier matching."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from screenagent.perception.ax import AXPerceiver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_app(localized_name: str, pid: int, bundle_path: str | None = None):
    app = MagicMock()
    app.localizedName.return_value = localized_name
    app.processIdentifier.return_value = pid
    if bundle_path:
        url = MagicMock()
        url.lastPathComponent.return_value = bundle_path
        app.bundleURL.return_value = url
    else:
        app.bundleURL.return_value = None
    return app


def _make_perceiver(apps: list) -> AXPerceiver:
    """Create an AXPerceiver with mocked workspace returning *apps*."""
    with patch("screenagent.perception.ax._ensure_ax_imports"):
        perceiver = AXPerceiver.__new__(AXPerceiver)

    mock_workspace = MagicMock()
    mock_workspace.runningApplications.return_value = apps

    import screenagent.perception.ax as ax_mod
    with patch.object(ax_mod, "_NSWorkspace", create=True) as mock_ns:
        mock_ns.sharedWorkspace.return_value = mock_workspace
        # We need _NSWorkspace to be set during the call, so patch the module global
        pass

    # Directly patch module-level _NSWorkspace for the duration of each test
    perceiver._mock_workspace = mock_workspace
    return perceiver


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFindAppPid:
    @pytest.fixture(autouse=True)
    def _setup_apps(self):
        self.apps = [
            _make_mock_app("System Settings", pid=100, bundle_path="System Settings.app"),
            _make_mock_app("Calculator", pid=200, bundle_path="Calculator.app"),
            _make_mock_app("Google Chrome", pid=300, bundle_path="Google Chrome.app"),
            _make_mock_app("Notes", pid=400, bundle_path="Notes.app"),
            _make_mock_app("Notification Notes", pid=500, bundle_path="Notification Notes.app"),
        ]
        mock_workspace = MagicMock()
        mock_workspace.runningApplications.return_value = self.apps
        mock_ns = MagicMock()
        mock_ns.sharedWorkspace.return_value = mock_workspace
        self._patcher = patch("screenagent.perception.ax._NSWorkspace", mock_ns)
        self._patcher.start()
        self._ax_patcher = patch("screenagent.perception.ax._ensure_ax_imports")
        self._ax_patcher.start()
        self.perceiver = AXPerceiver.__new__(AXPerceiver)

    @pytest.fixture(autouse=True)
    def _teardown(self):
        yield
        self._patcher.stop()
        self._ax_patcher.stop()

    def test_case_insensitive_exact(self):
        """'system settings' should match 'System Settings' via case-insensitive exact."""
        assert self.perceiver._find_app_pid("system settings") == 100

    def test_bundle_name_case_insensitive(self):
        """'calculator' should match Calculator.app bundle name."""
        assert self.perceiver._find_app_pid("calculator") == 200

    def test_substring_match(self):
        """'chrome' should match 'Google Chrome' via substring."""
        assert self.perceiver._find_app_pid("chrome") == 300

    def test_no_match_returns_none(self):
        """Non-existent app should return None."""
        assert self.perceiver._find_app_pid("NonExistentApp") is None

    def test_exact_preferred_over_substring(self):
        """'Notes' should match exact 'Notes' (PID 400), not substring 'Notification Notes' (PID 500)."""
        assert self.perceiver._find_app_pid("Notes") == 400

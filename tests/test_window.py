from __future__ import annotations

from unittest.mock import MagicMock, patch

from desktop_mcp.groups import window


class TestGateDisabledByDefault:
    def test_focus_window_refused(self):
        result = window.focus_window("Notepad")
        assert result["ok"] is False
        assert result["error"]["type"] == "policy_refusal"

    def test_move_resize_window_refused(self):
        result = window.move_resize_window("Notepad", 0, 0, 100, 100)
        assert result["ok"] is False
        assert result["error"]["type"] == "policy_refusal"

    def test_minimize_window_refused(self):
        result = window.minimize_window("Notepad")
        assert result["ok"] is False
        assert result["error"]["type"] == "policy_refusal"

    def test_restore_window_refused(self):
        result = window.restore_window("Notepad")
        assert result["ok"] is False
        assert result["error"]["type"] == "policy_refusal"


class TestFocusWindow:
    def test_success(self, enable_window):
        w = MagicMock(title="Notepad")
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = [w]
            result = window.focus_window("Notepad")
        assert result["ok"] is True
        w.activate.assert_called_once()

    def test_not_found(self, enable_window):
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = []
            result = window.focus_window("Ghost")
        assert result["ok"] is False
        assert result["error"]["type"] == "not_found"

    def test_uipi_failure_is_structured(self, enable_window):
        w = MagicMock(title="AdminApp")
        w.activate.side_effect = PermissionError("access denied")
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = [w]
            result = window.focus_window("AdminApp")
        assert result["ok"] is False
        assert result["error"]["type"] == "window_action_failed"
        assert "UIPI" in result["error"]["message"]


class TestMoveResizeWindow:
    def test_success(self, enable_window):
        w = MagicMock(title="Notepad", left=10, top=10, width=200, height=200)
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = [w]
            result = window.move_resize_window("Notepad", 10, 10, 200, 200)
        assert result["ok"] is True
        w.moveTo.assert_called_once_with(10, 10)
        w.resizeTo.assert_called_once_with(200, 200)

    def test_not_found(self, enable_window):
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = []
            result = window.move_resize_window("Ghost", 0, 0, 1, 1)
        assert result["ok"] is False

    def test_failure_is_structured(self, enable_window):
        w = MagicMock(title="AdminApp")
        w.moveTo.side_effect = RuntimeError("denied")
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = [w]
            result = window.move_resize_window("AdminApp", 0, 0, 1, 1)
        assert result["ok"] is False
        assert result["error"]["type"] == "window_action_failed"


class TestMinimizeRestore:
    def test_minimize_success(self, enable_window):
        w = MagicMock(title="Notepad")
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = [w]
            result = window.minimize_window("Notepad")
        assert result["ok"] is True
        w.minimize.assert_called_once()

    def test_restore_success(self, enable_window):
        w = MagicMock(title="Notepad")
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = [w]
            result = window.restore_window("Notepad")
        assert result["ok"] is True
        w.restore.assert_called_once()

    def test_minimize_not_found(self, enable_window):
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = []
            result = window.minimize_window("Ghost")
        assert result["ok"] is False

    def test_restore_not_found(self, enable_window):
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = []
            result = window.restore_window("Ghost")
        assert result["ok"] is False

    def test_minimize_failure_structured(self, enable_window):
        w = MagicMock(title="AdminApp")
        w.minimize.side_effect = RuntimeError("denied")
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = [w]
            result = window.minimize_window("AdminApp")
        assert result["ok"] is False
        assert result["error"]["type"] == "window_action_failed"

    def test_restore_failure_structured(self, enable_window):
        w = MagicMock(title="AdminApp")
        w.restore.side_effect = RuntimeError("denied")
        with patch.object(window, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = [w]
            result = window.restore_window("AdminApp")
        assert result["ok"] is False
        assert result["error"]["type"] == "window_action_failed"

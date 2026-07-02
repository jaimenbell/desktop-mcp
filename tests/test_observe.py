from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from desktop_mcp.groups import observe


def _make_fake_sct(monitors):
    sct = MagicMock()
    sct.monitors = monitors
    shot = MagicMock()
    shot.width = 100
    shot.height = 80
    shot.rgb = b"\x00" * (100 * 80 * 3)
    shot.size = (100, 80)
    sct.grab.return_value = shot
    sct.__enter__.return_value = sct
    sct.__exit__.return_value = False
    return sct, shot


class TestScreenshot:
    def test_full_desktop_default(self, tmp_scratch):
        sct, _ = _make_fake_sct([{"left": 0, "top": 0, "width": 1920, "height": 1080}])
        with patch.object(observe, "mss") as mock_mss:
            mock_mss.MSS.return_value = sct
            mock_mss.tools.to_png = MagicMock()
            result = observe.screenshot()
        assert result["ok"] is True
        assert result["w"] == 100
        assert result["h"] == 80
        assert result["monitor"] == 0
        assert result["path"].endswith(".png")

    def test_specific_monitor(self, tmp_scratch):
        sct, _ = _make_fake_sct(
            [{"left": 0, "top": 0, "width": 3000, "height": 1080}, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
        )
        with patch.object(observe, "mss") as mock_mss:
            mock_mss.MSS.return_value = sct
            mock_mss.tools.to_png = MagicMock()
            result = observe.screenshot(monitor=1)
        assert result["ok"] is True
        assert result["monitor"] == 1

    def test_monitor_out_of_range(self, tmp_scratch):
        sct, _ = _make_fake_sct([{"left": 0, "top": 0, "width": 1920, "height": 1080}])
        with patch.object(observe, "mss") as mock_mss:
            mock_mss.MSS.return_value = sct
            result = observe.screenshot(monitor=5)
        assert result["ok"] is False
        assert result["error"]["type"] == "capture_error"

    def test_region(self, tmp_scratch):
        sct, _ = _make_fake_sct([{"left": 0, "top": 0, "width": 1920, "height": 1080}])
        with patch.object(observe, "mss") as mock_mss:
            mock_mss.MSS.return_value = sct
            mock_mss.tools.to_png = MagicMock()
            result = observe.screenshot(region={"left": 10, "top": 10, "width": 200, "height": 150})
        assert result["ok"] is True
        sct.grab.assert_called_once_with({"left": 10, "top": 10, "width": 200, "height": 150})

    def test_window_title_found(self, tmp_scratch):
        sct, _ = _make_fake_sct([{"left": 0, "top": 0, "width": 1920, "height": 1080}])
        fake_win = MagicMock(left=5, top=5, width=300, height=200)
        with patch.object(observe, "mss") as mock_mss, patch.object(observe, "pygetwindow") as mock_pgw:
            mock_mss.MSS.return_value = sct
            mock_mss.tools.to_png = MagicMock()
            mock_pgw.getWindowsWithTitle.return_value = [fake_win]
            result = observe.screenshot(window_title="Notepad")
        assert result["ok"] is True
        sct.grab.assert_called_once_with({"left": 5, "top": 5, "width": 300, "height": 200})

    def test_window_title_not_found(self, tmp_scratch):
        with patch.object(observe, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = []
            result = observe.screenshot(window_title="NoSuchWindow")
        assert result["ok"] is False
        assert result["error"]["type"] == "not_found"

    def test_capture_exception_is_structured(self, tmp_scratch):
        with patch.object(observe, "mss") as mock_mss:
            mock_mss.MSS.side_effect = RuntimeError("boom")
            result = observe.screenshot()
        assert result["ok"] is False
        assert result["error"]["type"] == "capture_error"
        assert "boom" in result["error"]["message"]


class TestListWindows:
    def test_success(self):
        w1 = MagicMock(title="Notepad", left=0, top=0, width=100, height=100, isActive=True, isMinimized=False)
        w2 = MagicMock(title="", left=0, top=0, width=50, height=50, isActive=False, isMinimized=False)
        with patch.object(observe, "pygetwindow") as mock_pgw:
            mock_pgw.getAllWindows.return_value = [w1, w2]
            result = observe.list_windows()
        assert result["ok"] is True
        titles = [w["title"] for w in result["windows"]]
        assert "Notepad" in titles
        assert "" not in titles  # blank-title windows filtered out

    def test_error_is_structured(self):
        with patch.object(observe, "pygetwindow") as mock_pgw:
            mock_pgw.getAllWindows.side_effect = RuntimeError("enum failed")
            result = observe.list_windows()
        assert result["ok"] is False
        assert result["error"]["type"] == "enum_error"


class TestGetActiveWindow:
    def test_returns_window(self):
        w = MagicMock(title="Chrome", left=1, top=2, width=3, height=4, isActive=True, isMinimized=False)
        with patch.object(observe, "pygetwindow") as mock_pgw:
            mock_pgw.getActiveWindow.return_value = w
            result = observe.get_active_window()
        assert result["ok"] is True
        assert result["window"]["title"] == "Chrome"

    def test_returns_none_when_no_active_window(self):
        with patch.object(observe, "pygetwindow") as mock_pgw:
            mock_pgw.getActiveWindow.return_value = None
            result = observe.get_active_window()
        assert result["ok"] is True
        assert result["window"] is None

    def test_error_is_structured(self):
        with patch.object(observe, "pygetwindow") as mock_pgw:
            mock_pgw.getActiveWindow.side_effect = RuntimeError("x")
            result = observe.get_active_window()
        assert result["ok"] is False


class TestWindowInfo:
    def test_found(self):
        w = MagicMock(title="Terminal", left=0, top=0, width=10, height=10, isActive=False, isMinimized=False)
        with patch.object(observe, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = [w]
            result = observe.window_info("Term")
        assert result["ok"] is True
        assert result["window"]["title"] == "Terminal"

    def test_not_found(self):
        with patch.object(observe, "pygetwindow") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = []
            result = observe.window_info("NoMatch")
        assert result["ok"] is False
        assert result["error"]["type"] == "not_found"

from __future__ import annotations

from unittest.mock import patch

import pytest

from desktop_mcp.groups import input_tools

BOUNDS = {"left": 0, "top": 0, "width": 1920, "height": 1080}


@pytest.fixture(autouse=True)
def _fixed_bounds():
    with patch.object(input_tools, "_virtual_desktop_bounds", return_value=BOUNDS):
        yield


class TestGateDisabledByDefault:
    @pytest.mark.parametrize(
        "fn,args",
        [
            (input_tools.mouse_move, (100, 100)),
            (input_tools.mouse_click, ()),
            (input_tools.mouse_drag, (0, 0, 10, 10)),
            (input_tools.mouse_scroll, (1,)),
            (input_tools.key_press, ("a",)),
            (input_tools.hotkey, (["ctrl", "c"],)),
            (input_tools.type_text, ("hello",)),
        ],
    )
    def test_refused_when_input_disabled(self, fn, args):
        result = fn(*args)
        assert result["ok"] is False
        assert result["error"]["type"] == "policy_refusal"
        assert result["error"]["group"] == "input"


class TestMouseMove:
    def test_success(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_move(500, 500)
        assert result["ok"] is True
        mock_pag.moveTo.assert_called_once_with(500, 500, duration=0.0)

    def test_out_of_bounds(self, enable_input):
        with patch.object(input_tools, "pyautogui"):
            result = input_tools.mouse_move(9999, 9999)
        assert result["ok"] is False
        assert result["error"]["type"] == "out_of_bounds"

    def test_pyautogui_exception_structured(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            mock_pag.moveTo.side_effect = RuntimeError("failsafe triggered")
            result = input_tools.mouse_move(100, 100)
        assert result["ok"] is False
        assert result["error"]["type"] == "input_failed"


class TestMouseClick:
    def test_success_with_coords(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_click(x=10, y=10, button="left", clicks=2)
        assert result["ok"] is True
        mock_pag.click.assert_called_once_with(x=10, y=10, button="left", clicks=2)

    def test_success_no_coords(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_click()
        assert result["ok"] is True

    def test_out_of_bounds(self, enable_input):
        with patch.object(input_tools, "pyautogui"):
            result = input_tools.mouse_click(x=-5, y=-5)
        assert result["ok"] is False
        assert result["error"]["type"] == "out_of_bounds"

    def test_out_of_bounds_x_only(self, enable_input):
        """x given without y still gets bounds-checked (was skipped pre-fix)."""
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_click(x=99999, y=None)
        assert result["ok"] is False
        assert result["error"]["type"] == "out_of_bounds"
        mock_pag.click.assert_not_called()

    def test_out_of_bounds_y_only(self, enable_input):
        """y given without x still gets bounds-checked (was skipped pre-fix)."""
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_click(x=None, y=99999)
        assert result["ok"] is False
        assert result["error"]["type"] == "out_of_bounds"
        mock_pag.click.assert_not_called()

    def test_success_x_only_in_bounds(self, enable_input):
        """A single valid coordinate is accepted and passed through untouched."""
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_click(x=10, y=None)
        assert result["ok"] is True
        mock_pag.click.assert_called_once_with(x=10, y=None, button="left", clicks=1)

    def test_success_both_none_is_current_position_mode(self, enable_input):
        """Both x and y None is the documented 'click at current cursor
        position' mode (pyautogui._normalizeXYArgs falls back to
        position()) and intentionally skips bounds validation."""
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_click(x=None, y=None)
        assert result["ok"] is True
        mock_pag.click.assert_called_once_with(x=None, y=None, button="left", clicks=1)


class TestMouseDrag:
    def test_success(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_drag(10, 10, 100, 100)
        assert result["ok"] is True
        mock_pag.dragTo.assert_called_once()

    def test_out_of_bounds_endpoint(self, enable_input):
        with patch.object(input_tools, "pyautogui"):
            result = input_tools.mouse_drag(10, 10, 99999, 99999)
        assert result["ok"] is False
        assert result["error"]["type"] == "out_of_bounds"


class TestMouseScroll:
    def test_success(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_scroll(5)
        assert result["ok"] is True
        mock_pag.scroll.assert_called_once_with(5, x=None, y=None)

    def test_out_of_bounds(self, enable_input):
        with patch.object(input_tools, "pyautogui"):
            result = input_tools.mouse_scroll(1, x=-1, y=-1)
        assert result["ok"] is False

    def test_out_of_bounds_x_only(self, enable_input):
        """x given without y still gets bounds-checked (was skipped pre-fix)."""
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_scroll(1, x=99999, y=None)
        assert result["ok"] is False
        assert result["error"]["type"] == "out_of_bounds"
        mock_pag.scroll.assert_not_called()

    def test_out_of_bounds_y_only(self, enable_input):
        """y given without x still gets bounds-checked (was skipped pre-fix)."""
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_scroll(1, x=None, y=99999)
        assert result["ok"] is False
        assert result["error"]["type"] == "out_of_bounds"
        mock_pag.scroll.assert_not_called()

    def test_success_both_none_is_current_position_mode(self, enable_input):
        """Both x and y None scrolls at the current cursor position and
        intentionally skips bounds validation."""
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.mouse_scroll(5, x=None, y=None)
        assert result["ok"] is True
        mock_pag.scroll.assert_called_once_with(5, x=None, y=None)


class TestKeyPress:
    def test_success(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.key_press("enter")
        assert result["ok"] is True
        mock_pag.press.assert_called_once_with("enter")

    def test_failure_structured(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            mock_pag.press.side_effect = RuntimeError("bad key")
            result = input_tools.key_press("bogus")
        assert result["ok"] is False
        assert result["error"]["type"] == "input_failed"


class TestHotkey:
    def test_success(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.hotkey(["ctrl", "c"])
        assert result["ok"] is True
        mock_pag.hotkey.assert_called_once_with("ctrl", "c")


class TestTypeText:
    def test_success(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            result = input_tools.type_text("hello world")
        assert result["ok"] is True
        assert result["length"] == 11
        mock_pag.typewrite.assert_called_once_with("hello world", interval=0.0)

    def test_failure_structured(self, enable_input):
        with patch.object(input_tools, "pyautogui") as mock_pag:
            mock_pag.typewrite.side_effect = RuntimeError("boom")
            result = input_tools.type_text("x")
        assert result["ok"] is False
        assert result["error"]["type"] == "input_failed"


class TestRateLimit:
    def test_exceeding_limit_returns_rate_limited(self, enable_input, monkeypatch):
        monkeypatch.setenv("DESKTOP_MCP_RATE_LIMIT_PER_MIN", "2")
        with patch.object(input_tools, "pyautogui"):
            r1 = input_tools.key_press("a")
            r2 = input_tools.key_press("a")
            r3 = input_tools.key_press("a")
        assert r1["ok"] is True
        assert r2["ok"] is True
        assert r3["ok"] is False
        assert r3["error"]["type"] == "rate_limited"

    def test_rate_limit_is_per_group_not_per_tool(self, enable_input, monkeypatch):
        """Different input tools share the input group's single bucket."""
        monkeypatch.setenv("DESKTOP_MCP_RATE_LIMIT_PER_MIN", "1")
        with patch.object(input_tools, "pyautogui"):
            r1 = input_tools.mouse_move(100, 100)
            r2 = input_tools.key_press("a")
        assert r1["ok"] is True
        assert r2["ok"] is False
        assert r2["error"]["type"] == "rate_limited"

    def test_default_limit_is_60(self):
        from desktop_mcp import config

        assert config.DEFAULT_RATE_LIMIT_PER_MIN == 60

"""Input group: mouse + keyboard. Env-gated behind DESKTOP_MCP_ENABLE_INPUT
(OFF by default) and rate-limited (default 60 actions/min, see config.py).

Named input_tools.py (not input.py) to avoid shadowing the builtin `input`.

pyautogui.FAILSAFE stays True: slamming the cursor into a screen corner
aborts in-flight pyautogui calls -- an intentional, if occasionally
inconvenient, human kill-switch. See plan's Open questions.
"""
from __future__ import annotations

import ctypes
import functools

import pyautogui

from .. import config

pyautogui.FAILSAFE = True

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def _virtual_desktop_bounds() -> dict:
    gsm = ctypes.windll.user32.GetSystemMetrics
    left = gsm(SM_XVIRTUALSCREEN)
    top = gsm(SM_YVIRTUALSCREEN)
    width = gsm(SM_CXVIRTUALSCREEN)
    height = gsm(SM_CYVIRTUALSCREEN)
    return {"left": left, "top": top, "width": width, "height": height}


def _validate_point(x: int | None, y: int | None) -> dict | None:
    """Bounds-check whichever of x/y is provided, independently.

    Both None is a legitimate "act at current cursor position" mode
    (pyautogui._normalizeXYArgs falls back to the live cursor position for
    a missing coordinate) and intentionally skips validation. A single
    coordinate is still validated against its own axis so e.g.
    x=99999, y=None can't slip past the bounds check.
    """
    if x is None and y is None:
        return None
    b = _virtual_desktop_bounds()
    if x is not None and not (b["left"] <= x <= b["left"] + b["width"]):
        return {
            "ok": False,
            "error": {
                "type": "out_of_bounds",
                "message": f"X coordinate {x} is outside the virtual desktop bounds {b}.",
                "bounds": b,
            },
        }
    if y is not None and not (b["top"] <= y <= b["top"] + b["height"]):
        return {
            "ok": False,
            "error": {
                "type": "out_of_bounds",
                "message": f"Y coordinate {y} is outside the virtual desktop bounds {b}.",
                "bounds": b,
            },
        }
    return None


def _catch_input_errors(fn):
    """Shared exception boundary for pyautogui calls: converts any exception
    raised during the actual input action into the same structured
    {"ok": False, "error": {"type": "input_failed", ...}} shape every tool
    below previously duplicated in its own try/except. Validation errors
    (out_of_bounds) are returned before this runs, so they're unaffected."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": {"type": "input_failed", "message": str(exc)}}

    return wrapper


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
@_catch_input_errors
def mouse_move(x: int, y: int, duration: float = 0.0) -> dict:
    err = _validate_point(x, y)
    if err:
        return err
    pyautogui.moveTo(x, y, duration=duration)
    return {"ok": True, "x": x, "y": y}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
@_catch_input_errors
def mouse_click(x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1) -> dict:
    err = _validate_point(x, y)
    if err:
        return err
    pyautogui.click(x=x, y=y, button=button, clicks=clicks)
    return {"ok": True, "x": x, "y": y, "button": button, "clicks": clicks}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
@_catch_input_errors
def mouse_drag(x1: int, y1: int, x2: int, y2: int, button: str = "left", duration: float = 0.2) -> dict:
    for x, y in ((x1, y1), (x2, y2)):
        err = _validate_point(x, y)
        if err:
            return err
    pyautogui.moveTo(x1, y1)
    pyautogui.dragTo(x2, y2, duration=duration, button=button)
    return {"ok": True, "from": [x1, y1], "to": [x2, y2], "button": button}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
@_catch_input_errors
def mouse_scroll(clicks: int, x: int | None = None, y: int | None = None) -> dict:
    err = _validate_point(x, y)
    if err:
        return err
    pyautogui.scroll(clicks, x=x, y=y)
    return {"ok": True, "clicks": clicks, "x": x, "y": y}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
@_catch_input_errors
def key_press(key: str) -> dict:
    pyautogui.press(key)
    return {"ok": True, "key": key}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
@_catch_input_errors
def hotkey(keys: list[str]) -> dict:
    pyautogui.hotkey(*keys)
    return {"ok": True, "keys": keys}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
@_catch_input_errors
def type_text(text: str, interval: float = 0.0) -> dict:
    pyautogui.typewrite(text, interval=interval)
    return {"ok": True, "length": len(text)}

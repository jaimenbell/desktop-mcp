"""Input group: mouse + keyboard. Env-gated behind DESKTOP_MCP_ENABLE_INPUT
(OFF by default) and rate-limited (default 60 actions/min, see config.py).

Named input_tools.py (not input.py) to avoid shadowing the builtin `input`.

pyautogui.FAILSAFE stays True: slamming the cursor into a screen corner
aborts in-flight pyautogui calls -- an intentional, if occasionally
inconvenient, human kill-switch. See plan's Open questions.
"""
from __future__ import annotations

import ctypes

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


def _validate_point(x: int, y: int) -> dict | None:
    b = _virtual_desktop_bounds()
    if not (b["left"] <= x <= b["left"] + b["width"] and b["top"] <= y <= b["top"] + b["height"]):
        return {
            "ok": False,
            "error": {
                "type": "out_of_bounds",
                "message": f"Point ({x}, {y}) is outside the virtual desktop bounds {b}.",
                "bounds": b,
            },
        }
    return None


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
def mouse_move(x: int, y: int, duration: float = 0.0) -> dict:
    err = _validate_point(x, y)
    if err:
        return err
    try:
        pyautogui.moveTo(x, y, duration=duration)
        return {"ok": True, "x": x, "y": y}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "input_failed", "message": str(exc)}}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
def mouse_click(x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1) -> dict:
    if x is not None and y is not None:
        err = _validate_point(x, y)
        if err:
            return err
    try:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return {"ok": True, "x": x, "y": y, "button": button, "clicks": clicks}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "input_failed", "message": str(exc)}}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
def mouse_drag(x1: int, y1: int, x2: int, y2: int, button: str = "left", duration: float = 0.2) -> dict:
    for x, y in ((x1, y1), (x2, y2)):
        err = _validate_point(x, y)
        if err:
            return err
    try:
        pyautogui.moveTo(x1, y1)
        pyautogui.dragTo(x2, y2, duration=duration, button=button)
        return {"ok": True, "from": [x1, y1], "to": [x2, y2], "button": button}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "input_failed", "message": str(exc)}}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
def mouse_scroll(clicks: int, x: int | None = None, y: int | None = None) -> dict:
    if x is not None and y is not None:
        err = _validate_point(x, y)
        if err:
            return err
    try:
        pyautogui.scroll(clicks, x=x, y=y)
        return {"ok": True, "clicks": clicks, "x": x, "y": y}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "input_failed", "message": str(exc)}}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
def key_press(key: str) -> dict:
    try:
        pyautogui.press(key)
        return {"ok": True, "key": key}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "input_failed", "message": str(exc)}}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
def hotkey(keys: list[str]) -> dict:
    try:
        pyautogui.hotkey(*keys)
        return {"ok": True, "keys": keys}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "input_failed", "message": str(exc)}}


@config.gated(config.GROUP_INPUT, rate_limited_group=True)
def type_text(text: str, interval: float = 0.0) -> dict:
    try:
        pyautogui.typewrite(text, interval=interval)
        return {"ok": True, "length": len(text)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "input_failed", "message": str(exc)}}

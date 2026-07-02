"""Window group: focus/move/resize/minimize/restore. Env-gated behind
DESKTOP_MCP_ENABLE_WINDOW (checked by server.py before these are called).

UIPI (User Interface Privilege Isolation) means a medium-integrity process
cannot manipulate a higher-integrity (elevated) window -- Windows silently or
loudly rejects it depending on the call. We surface that as a clean
structured error naming the limitation, never a silent no-op.
"""
from __future__ import annotations

from typing import Any

import pygetwindow

from .. import config

_UIPI_HINT = (
    "This may be an elevated/admin window -- UIPI prevents a non-elevated "
    "process from controlling it. See README limitations."
)


def _find_window(title_substr: str) -> Any | None:
    matches = pygetwindow.getWindowsWithTitle(title_substr)
    return matches[0] if matches else None


def _not_found(title_substr: str) -> dict:
    return {"ok": False, "error": {"type": "not_found", "message": f"No window matching '{title_substr}'"}}


def _uipi_error(action: str, exc: Exception) -> dict:
    return {
        "ok": False,
        "error": {
            "type": "window_action_failed",
            "message": f"{action} failed: {exc}. {_UIPI_HINT}",
        },
    }


@config.gated(config.GROUP_WINDOW)
def focus_window(title_substr: str) -> dict:
    win = _find_window(title_substr)
    if win is None:
        return _not_found(title_substr)
    try:
        win.activate()
        return {"ok": True, "title": win.title}
    except Exception as exc:  # noqa: BLE001
        return _uipi_error("focus_window", exc)


@config.gated(config.GROUP_WINDOW)
def move_resize_window(title_substr: str, x: int, y: int, width: int, height: int) -> dict:
    win = _find_window(title_substr)
    if win is None:
        return _not_found(title_substr)
    try:
        win.moveTo(x, y)
        win.resizeTo(width, height)
        return {"ok": True, "title": win.title, "left": win.left, "top": win.top, "width": win.width, "height": win.height}
    except Exception as exc:  # noqa: BLE001
        return _uipi_error("move_resize_window", exc)


@config.gated(config.GROUP_WINDOW)
def minimize_window(title_substr: str) -> dict:
    win = _find_window(title_substr)
    if win is None:
        return _not_found(title_substr)
    try:
        win.minimize()
        return {"ok": True, "title": win.title}
    except Exception as exc:  # noqa: BLE001
        return _uipi_error("minimize_window", exc)


@config.gated(config.GROUP_WINDOW)
def restore_window(title_substr: str) -> dict:
    win = _find_window(title_substr)
    if win is None:
        return _not_found(title_substr)
    try:
        win.restore()
        return {"ok": True, "title": win.title}
    except Exception as exc:  # noqa: BLE001
        return _uipi_error("restore_window", exc)

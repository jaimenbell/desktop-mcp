"""Observe group: screenshot + window-read. Always enabled (no env gate) --
these are read-only and considered safe by default.

Functions here are the pure/testable core; server.py wires them as MCP tools.
Backend libraries (mss, pygetwindow) are imported at module scope so tests can
monkeypatch `desktop_mcp.groups.observe.mss` / `.pygetwindow` directly.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import mss
import pygetwindow

from .. import paths


def _virtual_desktop_bounds(sct: Any) -> dict:
    """monitors[0] in mss is always the full virtual-desktop bounding box."""
    m = sct.monitors[0]
    return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}


def _resolve_monitor(sct: Any, monitor: int | None) -> dict:
    """monitor index: 0 = full virtual desktop, 1..N = physical monitor N."""
    monitors = sct.monitors
    if monitor is None:
        return monitors[0]
    if monitor < 0 or monitor >= len(monitors):
        raise ValueError(f"monitor index {monitor} out of range (0..{len(monitors) - 1})")
    return monitors[monitor]


def _window_to_dict(win: Any) -> dict:
    return {
        "title": win.title,
        "left": win.left,
        "top": win.top,
        "width": win.width,
        "height": win.height,
        "is_active": bool(getattr(win, "isActive", False)),
        "is_minimized": bool(getattr(win, "isMinimized", False)),
    }


def _find_window(title_substr: str) -> Any | None:
    matches = pygetwindow.getWindowsWithTitle(title_substr)
    return matches[0] if matches else None


def screenshot(
    monitor: int | None = None,
    region: dict | None = None,
    window_title: str | None = None,
    downscale_max_px: int | None = None,
) -> dict:
    """Capture a PNG. Precedence: window_title > region > monitor > full virtual desktop.

    Returns {ok, path, w, h, monitor} or a structured error.
    """
    try:
        with mss.mss() as sct:
            if window_title:
                win = _find_window(window_title)
                if win is None:
                    return {
                        "ok": False,
                        "error": {"type": "not_found", "message": f"No window matching '{window_title}'"},
                    }
                box = {"left": win.left, "top": win.top, "width": win.width, "height": win.height}
            elif region:
                box = region
            else:
                box = _resolve_monitor(sct, monitor)

            shot = sct.grab(box)
            w, h = shot.width, shot.height

            out_path = paths.scratch_dir() / f"screenshot-{uuid.uuid4().hex[:10]}.png"
            mss.tools.to_png(shot.rgb, shot.size, output=str(out_path))

            if downscale_max_px and max(w, h) > downscale_max_px:
                _downscale_png(out_path, downscale_max_px)

            return {
                "ok": True,
                "path": str(out_path),
                "w": w,
                "h": h,
                "monitor": monitor if monitor is not None else 0,
            }
    except Exception as exc:  # noqa: BLE001 - fail-soft
        return {"ok": False, "error": {"type": "capture_error", "message": str(exc)}}


def _downscale_png(path: Any, max_px: int) -> None:
    """Best-effort downscale using PIL if available; no-op otherwise (mss's
    own PNG writer has no resize option, and pulling in PIL as a hard dep
    just for this is out of scope for v1)."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as im:
            w, h = im.size
            scale = max_px / max(w, h)
            if scale < 1.0:
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
                im.save(path)
    except ImportError:
        pass


def list_windows() -> dict:
    try:
        wins = pygetwindow.getAllWindows()
        return {"ok": True, "windows": [_window_to_dict(w) for w in wins if w.title]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "enum_error", "message": str(exc)}}


def get_active_window() -> dict:
    try:
        win = pygetwindow.getActiveWindow()
        if win is None:
            return {"ok": True, "window": None}
        return {"ok": True, "window": _window_to_dict(win)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "enum_error", "message": str(exc)}}


def window_info(title_substr: str) -> dict:
    try:
        win = _find_window(title_substr)
        if win is None:
            return {"ok": False, "error": {"type": "not_found", "message": f"No window matching '{title_substr}'"}}
        return {"ok": True, "window": _window_to_dict(win)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "enum_error", "message": str(exc)}}


def _now() -> float:
    return time.time()

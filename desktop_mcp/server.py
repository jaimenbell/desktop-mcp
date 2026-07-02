#!/usr/bin/env python3
"""desktop-mcp -- Windows desktop-control MCP server (FastMCP).

Tool groups (see desktop_mcp.config): observe (always on), window, input,
record (input/window/record env-gated, OFF by default except where the
operator's ~/.claude.json registration enables them). Every window/input/
record tool enforces its own gate + (input only) rate limit at the function
level (desktop_mcp.config.gated), so this file is thin wiring -- the safety
logic lives in config.py and is unit-tested independently of the MCP
transport.

Run: python -m desktop_mcp.server
"""
from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from . import config
from .groups import input_tools, observe, record, window

SERVER_NAME = "desktop-mcp"

config.ensure_dpi_awareness()

mcp = FastMCP(SERVER_NAME)


# ---- observe (always on) ----------------------------------------------

@mcp.tool(name="screenshot", description="Capture a PNG screenshot of a monitor, region, or window. Returns {path, w, h, monitor}.")
async def screenshot_tool(
    monitor: Optional[int] = None,
    region: Optional[dict] = None,
    window_title: Optional[str] = None,
    downscale_max_px: Optional[int] = None,
) -> dict:
    return observe.screenshot(monitor=monitor, region=region, window_title=window_title, downscale_max_px=downscale_max_px)


@mcp.tool(name="list_windows", description="List all visible top-level windows with title and bounds.")
async def list_windows_tool() -> dict:
    return observe.list_windows()


@mcp.tool(name="get_active_window", description="Return the currently focused/active window, or null if none.")
async def get_active_window_tool() -> dict:
    return observe.get_active_window()


@mcp.tool(name="window_info", description="Look up a window by title substring; returns its bounds and state.")
async def window_info_tool(title_substr: str) -> dict:
    return observe.window_info(title_substr)


# ---- window (env-gated: DESKTOP_MCP_ENABLE_WINDOW) ---------------------

@mcp.tool(name="focus_window", description="Bring a window to the foreground by title substring. Requires DESKTOP_MCP_ENABLE_WINDOW=1.")
async def focus_window_tool(title_substr: str) -> dict:
    return window.focus_window(title_substr)


@mcp.tool(name="move_resize_window", description="Move and resize a window by title substring. Requires DESKTOP_MCP_ENABLE_WINDOW=1.")
async def move_resize_window_tool(title_substr: str, x: int, y: int, width: int, height: int) -> dict:
    return window.move_resize_window(title_substr, x, y, width, height)


@mcp.tool(name="minimize_window", description="Minimize a window by title substring. Requires DESKTOP_MCP_ENABLE_WINDOW=1.")
async def minimize_window_tool(title_substr: str) -> dict:
    return window.minimize_window(title_substr)


@mcp.tool(name="restore_window", description="Restore a minimized window by title substring. Requires DESKTOP_MCP_ENABLE_WINDOW=1.")
async def restore_window_tool(title_substr: str) -> dict:
    return window.restore_window(title_substr)


# ---- input (env-gated: DESKTOP_MCP_ENABLE_INPUT, OFF by default; rate-capped) --

@mcp.tool(name="mouse_move", description="Move the mouse cursor to (x, y) in virtual-desktop coordinates. Requires DESKTOP_MCP_ENABLE_INPUT=1.")
async def mouse_move_tool(x: int, y: int, duration: float = 0.0) -> dict:
    return input_tools.mouse_move(x, y, duration=duration)


@mcp.tool(name="mouse_click", description="Click the mouse at (x, y) or the current position. Requires DESKTOP_MCP_ENABLE_INPUT=1.")
async def mouse_click_tool(x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1) -> dict:
    return input_tools.mouse_click(x=x, y=y, button=button, clicks=clicks)


@mcp.tool(name="mouse_drag", description="Drag the mouse from (x1, y1) to (x2, y2). Requires DESKTOP_MCP_ENABLE_INPUT=1.")
async def mouse_drag_tool(x1: int, y1: int, x2: int, y2: int, button: str = "left", duration: float = 0.2) -> dict:
    return input_tools.mouse_drag(x1, y1, x2, y2, button=button, duration=duration)


@mcp.tool(name="mouse_scroll", description="Scroll the mouse wheel by `clicks` (positive=up) at an optional position. Requires DESKTOP_MCP_ENABLE_INPUT=1.")
async def mouse_scroll_tool(clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> dict:
    return input_tools.mouse_scroll(clicks, x=x, y=y)


@mcp.tool(name="key_press", description="Press a single key (pyautogui key name, e.g. 'enter', 'a'). Requires DESKTOP_MCP_ENABLE_INPUT=1.")
async def key_press_tool(key: str) -> dict:
    return input_tools.key_press(key)


@mcp.tool(name="hotkey", description="Press a key combination, e.g. ['ctrl', 'c']. Requires DESKTOP_MCP_ENABLE_INPUT=1.")
async def hotkey_tool(keys: list[str]) -> dict:
    return input_tools.hotkey(keys)


@mcp.tool(name="type_text", description="Type a string via simulated keystrokes. Requires DESKTOP_MCP_ENABLE_INPUT=1.")
async def type_text_tool(text: str, interval: float = 0.0) -> dict:
    return input_tools.type_text(text, interval=interval)


# ---- record (env-gated: DESKTOP_MCP_ENABLE_RECORD) ---------------------

@mcp.tool(name="record_start", description="Start an ffmpeg gdigrab screen recording with a hard max_duration_s cap. Requires DESKTOP_MCP_ENABLE_RECORD=1.")
async def record_start_tool(region: Optional[dict] = None, monitor: Optional[int] = None, fps: int = 30, max_duration_s: int = 300) -> dict:
    return record.record_start(region=region, monitor=monitor, fps=fps, max_duration_s=max_duration_s)


@mcp.tool(name="record_status", description="Check whether a recording is in progress. Requires DESKTOP_MCP_ENABLE_RECORD=1.")
async def record_status_tool() -> dict:
    return record.record_status()


@mcp.tool(name="record_stop", description="Stop the active recording and return {path, bytes, duration_s}. Requires DESKTOP_MCP_ENABLE_RECORD=1.")
async def record_stop_tool() -> dict:
    return record.record_stop()


if __name__ == "__main__":
    mcp.run()

from __future__ import annotations

import asyncio

from desktop_mcp.server import mcp

EXPECTED_V1_TOOLS = {
    "screenshot",
    "list_windows",
    "get_active_window",
    "focus_window",
    "move_resize_window",
    "mouse_move",
    "mouse_click",
    "mouse_drag",
    "mouse_scroll",
    "key_press",
    "hotkey",
    "type_text",
    "record_start",
    "record_status",
    "record_stop",
}


def _list_tools():
    return asyncio.run(mcp.list_tools())


def test_all_v1_tools_registered():
    tools = _list_tools()
    names = {t.name for t in tools}
    missing = EXPECTED_V1_TOOLS - names
    assert not missing, f"missing v1 tools: {missing}"


def test_tool_count_at_least_v1_set():
    tools = _list_tools()
    assert len(tools) >= len(EXPECTED_V1_TOOLS)


def test_every_tool_has_description():
    tools = _list_tools()
    for t in tools:
        assert t.description, f"tool {t.name} missing a description"

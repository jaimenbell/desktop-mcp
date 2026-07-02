"""Real-hardware smoke tests. Skipped unless DESKTOP_MCP_LIVE=1.

These observe/record only -- screenshot and screen-recording. Per project
safety rails, NO live input-injection smoke exists anywhere in this suite;
input tools are exercised only via mocks (see test_input.py).
"""
from __future__ import annotations

import ctypes
import os
import time

import pytest

from desktop_mcp.groups import observe, record

LIVE = os.environ.get("DESKTOP_MCP_LIVE") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set DESKTOP_MCP_LIVE=1 to run real-hardware smoke tests")


def _virtual_desktop_dims():
    gsm = ctypes.windll.user32.GetSystemMetrics
    return gsm(78), gsm(79)  # SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN


@pytest.mark.live
def test_live_screenshot_real_png(tmp_path, monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_SCRATCH_DIR", str(tmp_path))
    result = observe.screenshot()
    assert result["ok"] is True, result

    path = result["path"]
    assert os.path.exists(path)
    size = os.path.getsize(path)
    assert size > 10_000, f"expected >10KB PNG, got {size} bytes"

    with open(path, "rb") as f:
        header = f.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"

    exp_w, exp_h = _virtual_desktop_dims()
    assert result["w"] == exp_w
    assert result["h"] == exp_h


@pytest.mark.live
def test_live_record_real_mp4(tmp_path, monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_SCRATCH_DIR", str(tmp_path))
    monkeypatch.setenv("DESKTOP_MCP_ENABLE_RECORD", "1")

    start = record.record_start(fps=15, max_duration_s=30)
    assert start["ok"] is True, start

    time.sleep(3)

    stop = record.record_stop()
    assert stop["ok"] is True, stop
    assert os.path.exists(stop["path"])
    assert stop["bytes"] > 0
    assert stop["duration_s"] is not None
    assert stop["duration_s"] >= 2.0, f"expected >=2s recording, ffprobe reported {stop['duration_s']}"

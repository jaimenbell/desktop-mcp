"""Record group: ffmpeg gdigrab screen recording. Env-gated behind
DESKTOP_MCP_ENABLE_RECORD.

record_start spawns `ffmpeg -f gdigrab ...` with a hard -t cap (max_duration_s)
so a forgotten recording can't run forever. record_stop sends a graceful 'q'
over stdin (ffmpeg's documented quit key) so the mp4 moov atom gets finalized
properly, falling back to terminate/kill if ffmpeg doesn't exit in time.

State (pid + meta) is persisted to scratch_dir()/record.meta.json so a stale
recorder from a crashed prior process can be detected and killed on the next
record_start (orphan-guard) -- not just tracked in this process's memory.
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import mss

from .. import config, paths

STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Holds the live Popen handle for the recording started by *this* process
# (if any). The on-disk meta file is the cross-process source of truth used
# for the orphan-guard; this is just so record_stop can talk to stdin.
_STATE: dict[str, Any] = {"popen": None}


def _meta_path() -> Path:
    return paths.scratch_dir() / "record.meta.json"


def _write_meta(meta: dict) -> None:
    _meta_path().write_text(json.dumps(meta), encoding="utf-8")


def _read_meta() -> dict | None:
    p = _meta_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _clear_meta() -> None:
    p = _meta_path()
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def _pid_alive(pid: int) -> bool:
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        return bool(ok) and exit_code.value == STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _kill_pid(pid: int) -> None:
    handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)  # PROCESS_TERMINATE
    if handle:
        try:
            ctypes.windll.kernel32.TerminateProcess(handle, 1)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)


def _orphan_guard() -> None:
    meta = _read_meta()
    if meta and _pid_alive(meta.get("pid", -1)):
        _kill_pid(meta["pid"])
    _clear_meta()
    _STATE["popen"] = None


def _resolve_monitor_region(monitor: int) -> dict:
    """Resolve a monitor index (0 = full virtual desktop, 1..N = physical
    monitor N) to a gdigrab-compatible region dict, same convention as
    observe._resolve_monitor. Raises ValueError if out of range."""
    with mss.MSS() as sct:
        monitors = sct.monitors
        if monitor < 0 or monitor >= len(monitors):
            raise ValueError(f"monitor index {monitor} out of range (0..{len(monitors) - 1})")
        m = monitors[monitor]
        return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}


def _build_cmd(out_path: Path, region: dict | None, fps: int, max_duration_s: int) -> list[str]:
    cmd = ["ffmpeg", "-y", "-f", "gdigrab", "-framerate", str(fps)]
    if region:
        cmd += ["-offset_x", str(region["left"]), "-offset_y", str(region["top"])]
        cmd += ["-video_size", f"{region['width']}x{region['height']}"]
    cmd += ["-i", "desktop", "-t", str(max_duration_s), str(out_path)]
    return cmd


@config.gated(config.GROUP_RECORD)
def record_start(region: dict | None = None, monitor: int | None = None, fps: int = 30, max_duration_s: int = 300) -> dict:
    _orphan_guard()

    if region is None and monitor is not None:
        try:
            region = _resolve_monitor_region(monitor)
        except (ValueError, Exception) as exc:  # noqa: BLE001 - mss/OS failure or bad index
            return {"ok": False, "error": {"type": "invalid_monitor", "message": str(exc)}}

    out_path = paths.scratch_dir() / f"recording-{int(time.time())}.mp4"
    cmd = _build_cmd(out_path, region, fps, max_duration_s)

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"type": "record_start_failed", "message": str(exc)}}

    _STATE["popen"] = proc
    _write_meta(
        {
            "pid": proc.pid,
            "path": str(out_path),
            "started_at": time.time(),
            "fps": fps,
            "max_duration_s": max_duration_s,
            "region": region,
        }
    )
    return {"ok": True, "path": str(out_path), "pid": proc.pid, "fps": fps, "max_duration_s": max_duration_s}


@config.gated(config.GROUP_RECORD)
def record_status() -> dict:
    meta = _read_meta()
    if meta is None:
        return {"ok": True, "status": "idle"}
    alive = _pid_alive(meta.get("pid", -1))
    if not alive:
        return {"ok": True, "status": "stopped", "path": meta.get("path")}
    elapsed = time.time() - meta.get("started_at", time.time())
    return {"ok": True, "status": "recording", "path": meta.get("path"), "elapsed_s": round(elapsed, 2)}


@config.gated(config.GROUP_RECORD)
def record_stop(timeout_s: float = 10.0) -> dict:
    meta = _read_meta()
    if meta is None:
        return {"ok": False, "error": {"type": "not_recording", "message": "No active recording."}}

    path = meta["path"]
    pid = meta.get("pid")
    proc = _STATE.get("popen")

    if proc is not None and proc.poll() is None:
        try:
            proc.communicate(input=b"q", timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    elif pid is not None and _pid_alive(pid):
        # No in-process handle (e.g. server restarted) -- best effort kill.
        _kill_pid(pid)
        time.sleep(0.5)

    _clear_meta()
    _STATE["popen"] = None

    return _probe_result(path)


def _probe_result(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": {"type": "record_missing_output", "message": f"Expected output not found: {path}"}}
    size_bytes = p.stat().st_size
    duration_s = _ffprobe_duration(path)
    return {"ok": True, "path": path, "bytes": size_bytes, "duration_s": duration_s}


def _ffprobe_duration(path: str) -> float | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return round(float(result.stdout.strip()), 2)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return None

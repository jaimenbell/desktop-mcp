from __future__ import annotations

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from desktop_mcp.groups import record


@pytest.fixture(autouse=True)
def _reset_record_state(tmp_scratch):
    record._STATE["popen"] = None
    yield
    record._STATE["popen"] = None


class TestGateDisabledByDefault:
    def test_record_start_refused(self):
        result = record.record_start()
        assert result["ok"] is False
        assert result["error"]["type"] == "policy_refusal"

    def test_record_status_refused(self):
        result = record.record_status()
        assert result["ok"] is False
        assert result["error"]["type"] == "policy_refusal"

    def test_record_stop_refused(self):
        result = record.record_stop()
        assert result["ok"] is False
        assert result["error"]["type"] == "policy_refusal"


class TestPidAlive:
    def test_current_process_is_alive(self):
        assert record._pid_alive(os.getpid()) is True

    def test_bogus_pid_is_not_alive(self):
        assert record._pid_alive(999_999_999) is False


class TestResolveMonitorRegion:
    def test_success(self):
        fake_sct = MagicMock()
        fake_sct.monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        fake_sct.__enter__.return_value = fake_sct
        fake_sct.__exit__.return_value = False
        with patch.object(record.mss, "MSS", return_value=fake_sct):
            region = record._resolve_monitor_region(1)
        assert region == {"left": 0, "top": 0, "width": 1920, "height": 1080}

    def test_out_of_range_raises(self):
        fake_sct = MagicMock()
        fake_sct.monitors = [{"left": 0, "top": 0, "width": 3840, "height": 1080}]
        fake_sct.__enter__.return_value = fake_sct
        fake_sct.__exit__.return_value = False
        with patch.object(record.mss, "MSS", return_value=fake_sct):
            with pytest.raises(ValueError):
                record._resolve_monitor_region(5)


class TestBuildCmd:
    def test_full_desktop(self, tmp_scratch):
        cmd = record._build_cmd(tmp_scratch / "out.mp4", None, 30, 60)
        assert "gdigrab" in cmd
        assert "-t" in cmd
        assert str(60) in cmd
        assert "-offset_x" not in cmd

    def test_region(self, tmp_scratch):
        region = {"left": 10, "top": 20, "width": 640, "height": 480}
        cmd = record._build_cmd(tmp_scratch / "out.mp4", region, 30, 60)
        assert "-offset_x" in cmd
        assert "10" in cmd
        assert "640x480" in cmd


class TestRecordStart:
    def test_success(self, enable_record, tmp_scratch):
        fake_proc = MagicMock(pid=4242)
        with patch.object(record, "_orphan_guard"), patch.object(record.subprocess, "Popen", return_value=fake_proc) as mock_popen:
            result = record.record_start(fps=30, max_duration_s=10)
        assert result["ok"] is True
        assert result["pid"] == 4242
        mock_popen.assert_called_once()
        meta = json.loads(record._meta_path().read_text(encoding="utf-8"))
        assert meta["pid"] == 4242

    def test_popen_failure_structured(self, enable_record, tmp_scratch):
        with patch.object(record, "_orphan_guard"), patch.object(record.subprocess, "Popen", side_effect=OSError("no ffmpeg")):
            result = record.record_start()
        assert result["ok"] is False
        assert result["error"]["type"] == "record_start_failed"

    def test_monitor_resolves_to_region(self, enable_record, tmp_scratch):
        """monitor= is not silently ignored -- it resolves to a region and
        gets forwarded into the ffmpeg gdigrab offset/video_size args."""
        fake_proc = MagicMock(pid=777)
        fake_region = {"left": 1920, "top": 0, "width": 1920, "height": 1080}
        with patch.object(record, "_orphan_guard"), patch.object(
            record, "_resolve_monitor_region", return_value=fake_region
        ) as mock_resolve, patch.object(record.subprocess, "Popen", return_value=fake_proc) as mock_popen:
            result = record.record_start(monitor=2)
        mock_resolve.assert_called_once_with(2)
        assert result["ok"] is True
        cmd = mock_popen.call_args[0][0]
        assert "-offset_x" in cmd
        assert "1920" in cmd

    def test_explicit_region_takes_priority_over_monitor(self, enable_record, tmp_scratch):
        fake_proc = MagicMock(pid=778)
        region = {"left": 5, "top": 5, "width": 100, "height": 100}
        with patch.object(record, "_orphan_guard"), patch.object(record, "_resolve_monitor_region") as mock_resolve, patch.object(
            record.subprocess, "Popen", return_value=fake_proc
        ):
            result = record.record_start(region=region, monitor=1)
        mock_resolve.assert_not_called()
        assert result["ok"] is True

    def test_invalid_monitor_returns_structured_error(self, enable_record, tmp_scratch):
        with patch.object(record, "_orphan_guard"), patch.object(
            record, "_resolve_monitor_region", side_effect=ValueError("monitor index 9 out of range (0..2)")
        ):
            result = record.record_start(monitor=9)
        assert result["ok"] is False
        assert result["error"]["type"] == "invalid_monitor"

    def test_orphan_guard_kills_stale_recorder(self, enable_record, tmp_scratch):
        record._write_meta({"pid": 111, "path": "old.mp4", "started_at": time.time()})
        fake_proc = MagicMock(pid=222)
        with patch.object(record, "_pid_alive", return_value=True) as mock_alive, patch.object(
            record, "_kill_pid"
        ) as mock_kill, patch.object(record.subprocess, "Popen", return_value=fake_proc):
            result = record.record_start()
        mock_kill.assert_called_once_with(111)
        assert result["ok"] is True
        meta = json.loads(record._meta_path().read_text(encoding="utf-8"))
        assert meta["pid"] == 222


class TestRecordStatus:
    def test_idle_when_no_meta(self, enable_record, tmp_scratch):
        result = record.record_status()
        assert result == {"ok": True, "status": "idle"}

    def test_recording_when_pid_alive(self, enable_record, tmp_scratch):
        record._write_meta({"pid": os.getpid(), "path": "x.mp4", "started_at": time.time() - 3})
        result = record.record_status()
        assert result["ok"] is True
        assert result["status"] == "recording"
        assert result["elapsed_s"] >= 3

    def test_stopped_when_pid_dead(self, enable_record, tmp_scratch):
        record._write_meta({"pid": 999_999_999, "path": "x.mp4", "started_at": time.time()})
        result = record.record_status()
        assert result["ok"] is True
        assert result["status"] == "stopped"


class TestRecordStop:
    def test_no_active_recording(self, enable_record, tmp_scratch):
        result = record.record_stop()
        assert result["ok"] is False
        assert result["error"]["type"] == "not_recording"

    def test_graceful_stop_success(self, enable_record, tmp_scratch):
        out_path = tmp_scratch / "clip.mp4"
        out_path.write_bytes(b"0" * 2048)
        record._write_meta({"pid": 555, "path": str(out_path), "started_at": time.time()})
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        record._STATE["popen"] = fake_proc

        fake_ffprobe = MagicMock(stdout="3.50\n")
        with patch.object(record.subprocess, "run", return_value=fake_ffprobe):
            result = record.record_stop()

        fake_proc.communicate.assert_called_once()
        assert result["ok"] is True
        assert result["bytes"] == 2048
        assert result["duration_s"] == 3.5
        assert record._meta_path().exists() is False

    def test_timeout_falls_back_to_kill(self, enable_record, tmp_scratch):
        import subprocess as sp

        out_path = tmp_scratch / "clip.mp4"
        out_path.write_bytes(b"0" * 10)
        record._write_meta({"pid": 555, "path": str(out_path), "started_at": time.time()})
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        fake_proc.communicate.side_effect = sp.TimeoutExpired(cmd="ffmpeg", timeout=10)
        record._STATE["popen"] = fake_proc

        with patch.object(record.subprocess, "run", return_value=MagicMock(stdout="2.00\n")):
            result = record.record_stop()

        fake_proc.kill.assert_called_once()
        assert result["ok"] is True

    def test_missing_output_file_structured(self, enable_record, tmp_scratch):
        missing_path = str(tmp_scratch / "does_not_exist.mp4")
        record._write_meta({"pid": 555, "path": missing_path, "started_at": time.time()})
        record._STATE["popen"] = None
        with patch.object(record, "_pid_alive", return_value=False):
            result = record.record_stop()
        assert result["ok"] is False
        assert result["error"]["type"] == "record_missing_output"


class TestFfprobeDuration:
    def test_parses_duration(self, tmp_scratch):
        with patch.object(record.subprocess, "run", return_value=MagicMock(stdout="12.34\n")):
            assert record._ffprobe_duration("x.mp4") == 12.34

    def test_returns_none_on_bad_output(self, tmp_scratch):
        with patch.object(record.subprocess, "run", return_value=MagicMock(stdout="not-a-number")):
            assert record._ffprobe_duration("x.mp4") is None

    def test_returns_none_on_timeout(self, tmp_scratch):
        import subprocess as sp

        with patch.object(record.subprocess, "run", side_effect=sp.TimeoutExpired(cmd="ffprobe", timeout=15)):
            assert record._ffprobe_duration("x.mp4") is None

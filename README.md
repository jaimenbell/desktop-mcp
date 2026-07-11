# desktop-mcp

[![PyPI](https://img.shields.io/pypi/v/desktop-mcp)](https://pypi.org/project/desktop-mcp/)
[![MCP Registry](https://img.shields.io/badge/MCP%20Registry-io.github.jaimenbell%2Fdesktop--mcp-blue)](https://registry.modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![tests](https://img.shields.io/badge/tests-123%20%28121%20passing%2C%202%20skipped%29-brightgreen)](tests)

Windows desktop-control MCP server: screenshot, window management,
mouse/keyboard input, and ffmpeg screen-recording, config-gated by tool
group (**input off by default**) -- built to the same standard as
[mcp-factory](https://github.com/jaimenbell/mcp-factory) and rag-mcp: own
pyproject, fastmcp server, honest README, real test suite.

## Quickstart

```bash
pip install desktop-mcp
```

```jsonc
// ~/.claude.json (or any MCP-host stdio client config)
{
  "mcpServers": {
    "desktop-mcp": {
      "command": "desktop-mcp"
      // or: "command": "python", "args": ["-m", "desktop_mcp"]
    }
  }
}
```

`window`/`input`/`record` tool groups are env-gated -- `input` stays off
unless you explicitly opt in. See Env vars below for the full table.

## Tool groups

| Group | Tools | Default state |
|---|---|---|
| `observe` | `screenshot`, `list_windows`, `get_active_window`, `window_info` | always on |
| `window` | `focus_window`, `move_resize_window`, `minimize_window`, `restore_window` | env-gated, off unless `DESKTOP_MCP_ENABLE_WINDOW=1` |
| `input` | `mouse_move`, `mouse_click`, `mouse_drag`, `mouse_scroll`, `key_press`, `hotkey`, `type_text` | env-gated, **OFF by default** -- requires `DESKTOP_MCP_ENABLE_INPUT=1` |
| `record` | `record_start`, `record_status`, `record_stop` | env-gated, off unless `DESKTOP_MCP_ENABLE_RECORD=1` |

A disabled group returns a structured `policy_refusal` error (never a silent
no-op, never a crash). Input actions are additionally rate-capped (default 60
actions/min, tunable via `DESKTOP_MCP_RATE_LIMIT_PER_MIN`) -- exceeding the
cap returns a structured `rate_limited` error.

This is defense-in-depth: harness-level permission prompts are the first
gate, but the server itself refuses input/window/record actions unless its
own env explicitly enables them, so a misconfigured or overly-permissive
harness can't turn on capabilities the operator didn't opt into for this
process.

## Honest-capabilities table

Every claim below maps to the file that implements it and the test(s) that
verify it -- no capability is asserted without a corresponding
implementation + test.

| Claim | Implementation | Verified by |
|---|---|---|
| Capture a screenshot (monitor / region / window) as PNG | `desktop_mcp/groups/observe.py::screenshot` | `tests/test_observe.py::TestScreenshot`, live: `tests/test_live_smoke.py::test_live_screenshot_real_png` |
| Enumerate windows / get active window / look up by title | `desktop_mcp/groups/observe.py` | `tests/test_observe.py::TestListWindows`, `TestGetActiveWindow`, `TestWindowInfo` |
| Focus / move+resize / minimize / restore a window | `desktop_mcp/groups/window.py` | `tests/test_window.py` |
| Mouse move/click/drag/scroll, key press/hotkey, type text | `desktop_mcp/groups/input_tools.py` | `tests/test_input.py` (mocked pyautogui only -- see Limitations) |
| Screen recording via ffmpeg gdigrab, hard duration cap, graceful stop | `desktop_mcp/groups/record.py` | `tests/test_record.py`, live: `tests/test_live_smoke.py::test_live_record_real_mp4` |
| Input group OFF by default, structured refusal when disabled | `desktop_mcp/config.py::group_enabled`, `gated` | `tests/test_config.py::TestGroupEnabled`, `tests/test_input.py::TestGateDisabledByDefault` |
| Rate cap on input actions (default 60/min) | `desktop_mcp/config.py::TokenBucket`, `RateLimiterRegistry` | `tests/test_config.py::TestTokenBucket`, `tests/test_input.py::TestRateLimit` |
| DPI-awareness bootstrap (per-monitor-v2) so mss/pyautogui coords agree on scaled displays | `desktop_mcp/config.py::ensure_dpi_awareness` | `tests/test_config.py::TestDpiAwareness` (idempotency only; visual coord-agreement is not automated -- see Limitations) |
| Coordinate validation against virtual-desktop bounds before any mouse action | `desktop_mcp/groups/input_tools.py::_validate_point` | `tests/test_input.py` (out-of-bounds cases) |
| Orphan-guard: a stale recorder from a crashed process gets killed before a new one starts | `desktop_mcp/groups/record.py::_orphan_guard` | `tests/test_record.py::TestRecordStart::test_orphan_guard_kills_stale_recorder` |

## Limitations (read before relying on this)

- **UIPI (User Interface Privilege Isolation) -- protects window handles,
  not input.** A medium-integrity process (this server, unless you elevate
  it) cannot manipulate a *window* owned by a higher-integrity
  (elevated/admin) process: `focus_window`, `move_resize_window`,
  `minimize_window`, and `restore_window` go through `pygetwindow`'s
  window-handle APIs (`desktop_mcp/groups/window.py`), which Windows blocks
  under UIPI and which this server surfaces as a structured
  `window_action_failed` error naming UIPI, never a silent no-op.
  **Keyboard/mouse input tools ARE covered by UIPI too -- and worse, they
  fail silently.** `type_text`, `hotkey`, `key_press`, and the mouse actions
  (`desktop_mcp/groups/input_tools.py`) go through `pyautogui`, whose Windows
  backend actually calls the legacy `keybd_event`/`mouse_event` Win32
  functions (not `SendInput` -- `pyautogui` tried `SendInput` and reverted to
  the older calls; see `_pyautogui_win.py` in the installed package). Per
  Microsoft's own docs, UIPI applies to synthesized input generally:
  "[applications] are permitted to inject input only into applications that
  are at an equal or lesser integrity level" (MSDN `SendInput` reference),
  and critically, "neither `GetLastError` nor the return value will indicate
  the failure was caused by UIPI blocking." `keybd_event`/`mouse_event` are
  void-return legacy calls with no failure signal at all, so `pyautogui` (and
  this server) cannot detect a block even in principle: if an elevated
  window has focus, these tools report `{"ok": true}` while Windows silently
  discards the injected keystrokes/clicks -- no exception, no error field,
  nothing reaches the target. This is **worse** than the window-handle path
  above, which at least raises a structured `window_action_failed` error
  naming UIPI. There is no code-level bypass and no workaround short of
  running the server elevated (or not enabling the input group at all),
  which this project does not do or recommend. Operators should treat any
  elevated app that could plausibly have focus as **silently unreachable**
  by this server's input tools, not as a gap that lets them through.
  *Possible future enhancement (not implemented): detect the foreground
  window's integrity level before injecting and return a structured refusal
  instead of a false `{"ok": true}` -- tracked as a v2 idea, not a current
  capability.*
- **DPI scaling.** The server sets per-monitor-v2 DPI awareness at startup so
  `mss` pixel coordinates and `pyautogui` point coordinates should agree on
  scaled displays. This bootstrap is unit-tested for idempotency/no-crash
  only -- actual coordinate agreement on a live multi-DPI multi-monitor setup
  has not been automated-tested and should be spot-checked if you're
  targeting a non-100%-scaled monitor.
- **UAC secure desktop.** When Windows switches to the secure desktop (UAC
  elevation prompts, Ctrl+Alt+Del, lock screen), no process running on the
  regular desktop -- including this server -- can see or interact with it.
  Screenshots will show whatever was on the regular desktop before the
  switch; input calls will not reach the secure desktop at all.
- **Single machine, local only.** No network transport, no remote control.
  stdio only, spawned by the MCP host on the same machine.
- **Input group is off by default in this repo's own registration.** See
  `~/.claude.json`'s `desktop-mcp` entry -- `DESKTOP_MCP_ENABLE_INPUT` is not
  set there. Enabling it is a deliberate per-registration operator choice,
  not a code change.
- **pyautogui failsafe.** `FAILSAFE=True` is intentional: slamming the cursor
  into a screen corner mid-action raises inside pyautogui and aborts the
  call. This can interrupt an in-flight `mouse_drag`. Treated as acceptable
  v1 behavior (see plan's Open questions) -- it's a deliberate human
  kill-switch, not a bug.
- **No OCR / vision analysis.** Screenshots are raw PNGs; interpreting their
  content is the consumer's job, not this server's.
- **No clipboard tools.** Credential-adjacent surface, deferred to a v2 with
  its own safety design.
- **Not registered with the mcp-factory hub.** This ships as a standalone
  repo (own pyproject, own venv-free system-Python312 install), matching the
  rag-mcp model. Hub/registry integration is a v2 candidate.

## Env vars

| Var | Effect | Default |
|---|---|---|
| `DESKTOP_MCP_ENABLE_WINDOW` | enable the `window` tool group | unset (off) |
| `DESKTOP_MCP_ENABLE_INPUT` | enable the `input` tool group | unset (off) |
| `DESKTOP_MCP_ENABLE_RECORD` | enable the `record` tool group | unset (off) |
| `DESKTOP_MCP_RATE_LIMIT_PER_MIN` | input-group rate cap | `60` |
| `DESKTOP_MCP_SCRATCH_DIR` | where screenshots/recordings/pidfiles are written | `%TEMP%\desktop-mcp-scratch` |
| `DESKTOP_MCP_LIVE` | `1` to run real-hardware smoke tests (see Testing) | unset (skip) |

## Usage examples

```jsonc
// A tool call from the MCP host, illustrative -- not a shell command.
{"tool": "screenshot", "arguments": {"monitor": 0}}
// -> {"ok": true, "path": "C:\\Users\\...\\Temp\\desktop-mcp-scratch\\screenshot-....png", "w": 3840, "h": 1080, "monitor": 0}

{"tool": "record_start", "arguments": {"fps": 30, "max_duration_s": 30}}
// -> {"ok": true, "path": "...\\recording-....mp4", "pid": 12345, "fps": 30, "max_duration_s": 30}
{"tool": "record_stop", "arguments": {}}
// -> {"ok": true, "path": "...\\recording-....mp4", "bytes": 800560, "duration_s": 3.13}

// input group disabled (default):
{"tool": "mouse_click", "arguments": {"x": 500, "y": 500}}
// -> {"ok": false, "error": {"type": "policy_refusal", "group": "input", "required_env": "DESKTOP_MCP_ENABLE_INPUT", ...}}
```

## Testing

```
# unit suite (mocked backends, no real screen/input/recording touched)
python -m pytest -q

# handshake check -- prints every registered tool name
python scripts/list_tools.py

# real-hardware smokes (real screenshot PNG, real ~3s screen recording;
# never input-injection -- see safety rails above)
DESKTOP_MCP_LIVE=1 python -m pytest -q -k live_screenshot
DESKTOP_MCP_LIVE=1 python -m pytest -q -k live_record
```

## Install

```
pip install -r requirements.txt   # or: pip install .
# deps: fastmcp==3.4.2, mss==10.2.0, pyautogui==0.9.54, PyGetWindow==0.0.9, pywin32==312
# also requires ffmpeg + ffprobe on PATH for the record group
```

Registered in `~/.claude.json` as `desktop-mcp` (stdio, system Python312,
`observe`+`window`+`record` groups enabled, `input` group absent from env).


## Commercial support

Maintained by [Jaimen Bell](https://jaimenbell.dev). For production MCP integrations, custom servers, or agent-reliability work, see [jaimenbell.dev](https://jaimenbell.dev) or sponsor ongoing maintenance via [GitHub Sponsors](https://github.com/sponsors/jaimenbell).

<!-- MCP registry ownership marker -->
mcp-name: io.github.jaimenbell/desktop-mcp

"""Config/safety layer for desktop-mcp.

Tool-group gating + rate limiting + structured refusal errors + DPI-awareness
bootstrap. This is the server's own defense-in-depth layer: even if a caller
gets past harness permission prompts, the server itself refuses input/window/
record actions unless explicitly enabled via env, and caps input-action
throughput.

Groups:
  observe -- screenshot / window-read (always on, no gate)
  window  -- focus/move/resize/minimize/restore (env-gated)
  input   -- mouse/keyboard (env-gated, OFF by default)
  record  -- ffmpeg screen recording (env-gated)

Env vars:
  DESKTOP_MCP_ENABLE_INPUT=1   -- enable the input group
  DESKTOP_MCP_ENABLE_WINDOW=1  -- enable the window group
  DESKTOP_MCP_ENABLE_RECORD=1  -- enable the record group
  DESKTOP_MCP_RATE_LIMIT_PER_MIN=<int> -- input-action rate cap (default 60)
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from threading import Lock

DEFAULT_RATE_LIMIT_PER_MIN = 60

GROUP_OBSERVE = "observe"
GROUP_WINDOW = "window"
GROUP_INPUT = "input"
GROUP_RECORD = "record"

_ENV_GATES = {
    GROUP_WINDOW: "DESKTOP_MCP_ENABLE_WINDOW",
    GROUP_INPUT: "DESKTOP_MCP_ENABLE_INPUT",
    GROUP_RECORD: "DESKTOP_MCP_ENABLE_RECORD",
}


def _env_truthy(name: str) -> bool:
    val = os.environ.get(name, "")
    return val.strip().lower() in ("1", "true", "yes", "on")


def group_enabled(group: str) -> bool:
    """observe is always on; other groups require their env gate."""
    if group == GROUP_OBSERVE:
        return True
    env_name = _ENV_GATES.get(group)
    if env_name is None:
        return False
    return _env_truthy(env_name)


def policy_refusal(group: str, tool: str) -> dict:
    """Structured refusal payload for a disabled tool group."""
    env_name = _ENV_GATES.get(group, f"DESKTOP_MCP_ENABLE_{group.upper()}")
    return {
        "ok": False,
        "error": {
            "type": "policy_refusal",
            "message": (
                f"Tool group '{group}' is disabled. Set {env_name}=1 in the "
                f"server's environment to enable it."
            ),
            "group": group,
            "tool": tool,
            "required_env": env_name,
        },
    }


def rate_limited(group: str, tool: str, limit_per_min: int, retry_after_s: float) -> dict:
    """Structured rate-limit payload."""
    return {
        "ok": False,
        "error": {
            "type": "rate_limited",
            "message": (
                f"Rate limit exceeded for group '{group}': max {limit_per_min} "
                f"actions/min. Retry after ~{retry_after_s:.1f}s."
            ),
            "group": group,
            "tool": tool,
            "limit_per_min": limit_per_min,
            "retry_after_s": round(retry_after_s, 2),
        },
    }


@dataclass
class TokenBucket:
    """Simple token-bucket rate limiter, one bucket per gated group.

    Capacity == limit_per_min, refills continuously at limit_per_min / 60
    tokens/sec. Thread-safe (guards a single Lock) since MCP tool calls could
    in principle be dispatched concurrently by the host.
    """

    limit_per_min: int
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: Lock = field(init=False, default_factory=Lock, repr=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.limit_per_min)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        rate_per_s = self.limit_per_min / 60.0
        self._tokens = min(self.limit_per_min, self._tokens + elapsed * rate_per_s)

    def try_acquire(self) -> tuple[bool, float]:
        """Attempt to consume one token. Returns (allowed, retry_after_s)."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True, 0.0
            rate_per_s = self.limit_per_min / 60.0
            deficit = 1.0 - self._tokens
            retry_after = deficit / rate_per_s if rate_per_s > 0 else float("inf")
            return False, retry_after


class RateLimiterRegistry:
    """Holds one TokenBucket per group, keyed by the current configured limit.

    Recreates the bucket if the configured limit_per_min changes (e.g. tests
    that monkeypatch the env between calls), so limit changes take effect
    without needing a fresh process.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._limits: dict[str, int] = {}

    def acquire(self, group: str) -> tuple[bool, float, int]:
        limit = get_rate_limit_per_min()
        bucket = self._buckets.get(group)
        if bucket is None or self._limits.get(group) != limit:
            bucket = TokenBucket(limit_per_min=limit)
            self._buckets[group] = bucket
            self._limits[group] = limit
        allowed, retry_after = bucket.try_acquire()
        return allowed, retry_after, limit

    def reset(self) -> None:
        """Test helper: clear all buckets so each test starts fresh."""
        self._buckets.clear()
        self._limits.clear()


def get_rate_limit_per_min() -> int:
    raw = os.environ.get("DESKTOP_MCP_RATE_LIMIT_PER_MIN")
    if not raw:
        return DEFAULT_RATE_LIMIT_PER_MIN
    try:
        val = int(raw)
        return val if val > 0 else DEFAULT_RATE_LIMIT_PER_MIN
    except ValueError:
        return DEFAULT_RATE_LIMIT_PER_MIN


# Module-level singleton registry shared by all input-group tools within a
# process. Tests call `reset()` on this (or construct their own registry) to
# avoid cross-test bucket state leaking.
RATE_LIMITER = RateLimiterRegistry()


_dpi_bootstrapped = False


def ensure_dpi_awareness() -> None:
    """Set per-monitor-v2 DPI awareness so mss pixel coords line up with
    pyautogui point coords on scaled displays. Idempotent; no-op on failure
    (e.g. non-Windows, or already set by host process) and never raises --
    this is a best-effort bootstrap, not a safety boundary.
    """
    global _dpi_bootstrapped
    if _dpi_bootstrapped:
        return
    _dpi_bootstrapped = True
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
            return
        except (AttributeError, OSError):
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
    except Exception:  # noqa: BLE001 - best-effort only
        pass


def check_group(group: str, tool: str) -> dict | None:
    """Gate check for a tool call. Returns a structured refusal dict if the
    group is disabled, else None (caller proceeds)."""
    if not group_enabled(group):
        return policy_refusal(group, tool)
    return None


def check_rate_limit(group: str, tool: str) -> dict | None:
    """Rate-limit check for a gated action. Returns a structured rate_limited
    dict if the caller is over the cap, else None (caller proceeds)."""
    allowed, retry_after, limit = RATE_LIMITER.acquire(group)
    if not allowed:
        return rate_limited(group, tool, limit, retry_after)
    return None


def gated(group: str, *, rate_limited_group: bool = False):
    """Decorator applied directly to group-module functions so the policy
    gate (and, for input-group actions, the rate limiter) is enforced at the
    source -- not just in the MCP tool wrapper -- and is unit-testable without
    spinning up the fastmcp server.

    Order: group gate first (cheaper, and a disabled group shouldn't consume
    rate-limit budget), then rate limit if requested.
    """

    def decorator(fn):
        def wrapper(*args, **kwargs):
            refusal = check_group(group, fn.__name__)
            if refusal is not None:
                return refusal
            if rate_limited_group:
                limited = check_rate_limit(group, fn.__name__)
                if limited is not None:
                    return limited
            return fn(*args, **kwargs)

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        wrapper.__wrapped__ = fn
        return wrapper

    return decorator

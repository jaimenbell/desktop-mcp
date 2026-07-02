from __future__ import annotations

import time

import pytest

from desktop_mcp import config


class TestGroupEnabled:
    def test_observe_always_enabled(self):
        assert config.group_enabled(config.GROUP_OBSERVE) is True

    def test_window_disabled_by_default(self):
        assert config.group_enabled(config.GROUP_WINDOW) is False

    def test_input_disabled_by_default(self):
        assert config.group_enabled(config.GROUP_INPUT) is False

    def test_record_disabled_by_default(self):
        assert config.group_enabled(config.GROUP_RECORD) is False

    def test_window_enabled_via_env(self, enable_window):
        assert config.group_enabled(config.GROUP_WINDOW) is True

    def test_input_enabled_via_env(self, enable_input):
        assert config.group_enabled(config.GROUP_INPUT) is True

    def test_record_enabled_via_env(self, enable_record):
        assert config.group_enabled(config.GROUP_RECORD) is True

    @pytest.mark.parametrize("val", ["true", "TRUE", "yes", "on", "1"])
    def test_truthy_variants(self, monkeypatch, val):
        monkeypatch.setenv("DESKTOP_MCP_ENABLE_INPUT", val)
        assert config.group_enabled(config.GROUP_INPUT) is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "", "off"])
    def test_falsy_variants(self, monkeypatch, val):
        monkeypatch.setenv("DESKTOP_MCP_ENABLE_INPUT", val)
        assert config.group_enabled(config.GROUP_INPUT) is False

    def test_unknown_group_not_enabled(self):
        assert config.group_enabled("bogus") is False


class TestPolicyRefusal:
    def test_structure(self):
        payload = config.policy_refusal(config.GROUP_INPUT, "mouse_move")
        assert payload["ok"] is False
        assert payload["error"]["type"] == "policy_refusal"
        assert payload["error"]["group"] == "input"
        assert payload["error"]["tool"] == "mouse_move"
        assert payload["error"]["required_env"] == "DESKTOP_MCP_ENABLE_INPUT"

    def test_message_names_env_var(self):
        payload = config.policy_refusal(config.GROUP_RECORD, "record_start")
        assert "DESKTOP_MCP_ENABLE_RECORD" in payload["error"]["message"]


class TestRateLimited:
    def test_structure(self):
        payload = config.rate_limited(config.GROUP_INPUT, "key_press", 60, 1.234)
        assert payload["ok"] is False
        assert payload["error"]["type"] == "rate_limited"
        assert payload["error"]["limit_per_min"] == 60
        assert payload["error"]["retry_after_s"] == 1.23


class TestCheckGroup:
    def test_returns_none_when_enabled(self):
        assert config.check_group(config.GROUP_OBSERVE, "screenshot") is None

    def test_returns_refusal_when_disabled(self):
        result = config.check_group(config.GROUP_INPUT, "mouse_move")
        assert result is not None
        assert result["error"]["type"] == "policy_refusal"


class TestTokenBucket:
    def test_allows_up_to_capacity(self):
        bucket = config.TokenBucket(limit_per_min=5)
        for _ in range(5):
            allowed, _ = bucket.try_acquire()
            assert allowed is True

    def test_denies_after_capacity_exhausted(self):
        bucket = config.TokenBucket(limit_per_min=2)
        bucket.try_acquire()
        bucket.try_acquire()
        allowed, retry_after = bucket.try_acquire()
        assert allowed is False
        assert retry_after > 0

    def test_refills_over_time(self):
        bucket = config.TokenBucket(limit_per_min=60)  # 1/sec
        bucket._tokens = 0.0
        bucket._last_refill = time.monotonic() - 1.5
        allowed, _ = bucket.try_acquire()
        assert allowed is True


class TestRateLimiterRegistry:
    def test_get_rate_limit_default(self):
        assert config.get_rate_limit_per_min() == config.DEFAULT_RATE_LIMIT_PER_MIN

    def test_get_rate_limit_env_override(self, monkeypatch):
        monkeypatch.setenv("DESKTOP_MCP_RATE_LIMIT_PER_MIN", "5")
        assert config.get_rate_limit_per_min() == 5

    def test_get_rate_limit_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("DESKTOP_MCP_RATE_LIMIT_PER_MIN", "not-a-number")
        assert config.get_rate_limit_per_min() == config.DEFAULT_RATE_LIMIT_PER_MIN

    def test_get_rate_limit_negative_falls_back(self, monkeypatch):
        monkeypatch.setenv("DESKTOP_MCP_RATE_LIMIT_PER_MIN", "-5")
        assert config.get_rate_limit_per_min() == config.DEFAULT_RATE_LIMIT_PER_MIN

    def test_registry_acquire_respects_limit(self, monkeypatch):
        monkeypatch.setenv("DESKTOP_MCP_RATE_LIMIT_PER_MIN", "3")
        registry = config.RateLimiterRegistry()
        results = [registry.acquire("input")[0] for _ in range(4)]
        assert results == [True, True, True, False]

    def test_check_rate_limit_helper(self, monkeypatch):
        monkeypatch.setenv("DESKTOP_MCP_RATE_LIMIT_PER_MIN", "1")
        assert config.check_rate_limit(config.GROUP_INPUT, "key_press") is None
        result = config.check_rate_limit(config.GROUP_INPUT, "key_press")
        assert result is not None
        assert result["error"]["type"] == "rate_limited"


class TestGatedDecorator:
    def test_blocks_when_group_disabled(self):
        @config.gated(config.GROUP_INPUT)
        def fn():
            return {"ok": True, "called": True}

        result = fn()
        assert result["ok"] is False
        assert result["error"]["type"] == "policy_refusal"

    def test_passes_through_when_enabled(self, enable_input):
        @config.gated(config.GROUP_INPUT)
        def fn():
            return {"ok": True, "called": True}

        result = fn()
        assert result == {"ok": True, "called": True}

    def test_rate_limits_when_requested(self, enable_input, monkeypatch):
        monkeypatch.setenv("DESKTOP_MCP_RATE_LIMIT_PER_MIN", "1")

        @config.gated(config.GROUP_INPUT, rate_limited_group=True)
        def fn():
            return {"ok": True}

        assert fn()["ok"] is True
        second = fn()
        assert second["ok"] is False
        assert second["error"]["type"] == "rate_limited"

    def test_disabled_group_never_consumes_rate_budget(self, monkeypatch):
        monkeypatch.setenv("DESKTOP_MCP_RATE_LIMIT_PER_MIN", "1")

        @config.gated(config.GROUP_INPUT, rate_limited_group=True)
        def fn():
            return {"ok": True}

        # Called twice while disabled -- both refused on policy, not rate.
        first = fn()
        second = fn()
        assert first["error"]["type"] == "policy_refusal"
        assert second["error"]["type"] == "policy_refusal"

    def test_preserves_function_name(self):
        @config.gated(config.GROUP_INPUT)
        def my_tool():
            return {}

        assert my_tool.__name__ == "my_tool"


class TestDpiAwareness:
    def test_idempotent_no_raise(self):
        config.ensure_dpi_awareness()
        config.ensure_dpi_awareness()  # second call is a no-op, must not raise

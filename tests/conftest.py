"""Shared fixtures: every test gets a clean env-gate + rate-limiter slate so
gate/rate-limit tests never leak state across tests."""
from __future__ import annotations

import pytest

from desktop_mcp import config

_GATE_ENV_VARS = [
    "DESKTOP_MCP_ENABLE_WINDOW",
    "DESKTOP_MCP_ENABLE_INPUT",
    "DESKTOP_MCP_ENABLE_RECORD",
    "DESKTOP_MCP_RATE_LIMIT_PER_MIN",
]


@pytest.fixture(autouse=True)
def _clean_gate_state(monkeypatch):
    for var in _GATE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    config.RATE_LIMITER.reset()
    yield
    config.RATE_LIMITER.reset()


@pytest.fixture
def enable_window(monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_ENABLE_WINDOW", "1")


@pytest.fixture
def enable_input(monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_ENABLE_INPUT", "1")


@pytest.fixture
def enable_record(monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_ENABLE_RECORD", "1")


@pytest.fixture
def tmp_scratch(tmp_path, monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_SCRATCH_DIR", str(tmp_path))
    return tmp_path

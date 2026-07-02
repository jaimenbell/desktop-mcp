#!/usr/bin/env python3
"""Entrypoint for the desktop-mcp MCP server.

Run as a top-level script (e.g. `python run_server.py`) so the repo root
lands on sys.path[0] and the `desktop_mcp` package imports cleanly -- same
convention as rag-mcp's run_server.py, referenced directly from
~/.claude.json's stdio args (no `pip install -e .` required).
"""
from __future__ import annotations

from desktop_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()

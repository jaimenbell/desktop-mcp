"""Scratch-directory helpers. Screenshots and recordings land under a local
scratchpad dir (gitignored), never inside the repo tree proper."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def scratch_dir() -> Path:
    """Directory for generated artifacts (screenshots, recordings, pidfiles).

    Override with DESKTOP_MCP_SCRATCH_DIR; defaults to a stable subfolder of
    the system temp dir so repeated runs don't scatter files across %TEMP%.
    """
    override = os.environ.get("DESKTOP_MCP_SCRATCH_DIR")
    base = Path(override) if override else Path(tempfile.gettempdir()) / "desktop-mcp-scratch"
    base.mkdir(parents=True, exist_ok=True)
    return base

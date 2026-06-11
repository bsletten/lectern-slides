"""Helpers for the subprocess adapters (marp, quarto).

Both shell out to an external binary that may not be installed; ``tool_available``
backs each adapter's ``available()`` guard, and ``run_tool`` runs the command,
turning a non-zero exit or a missing binary into a user-facing :class:`RenderError`
that cites the tool and its captured stderr (never a raw traceback).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..errors import RenderError


def tool_available(binary: str) -> bool:
    """Whether ``binary`` is on ``PATH`` (backs an adapter's ``available()``)."""
    return shutil.which(binary) is not None


def run_tool(cmd: list[str], cwd: Path, *, tool: str) -> str:
    """Run ``cmd`` in ``cwd``; raise :class:`RenderError` on failure.

    Returns the captured stdout on success. The binary is invoked directly (no
    shell), so ``cmd`` arguments are passed verbatim.
    """
    try:
        proc = subprocess.run(  # noqa: S603 — args are built by us, no shell
            cmd, cwd=cwd, capture_output=True, text=True
        )
    except FileNotFoundError:
        raise RenderError(
            f"{tool} is not installed or not on PATH (looked for '{cmd[0]}')"
        ) from None
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise RenderError(f"{tool} failed (exit {proc.returncode}){suffix}")
    return proc.stdout

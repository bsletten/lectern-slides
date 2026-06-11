"""Full-document grayscale via Ghostscript (the ``ghostscript`` B&W engine).

Post-processes a finished PDF to DeviceGray, converting *everything* including
raster images and captured posters — the cases the vector ``tokens`` engine
deliberately leaves alone. Needs the external ``gs`` binary; the caller checks
:func:`available` first and degrades with a warning when it's absent.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..errors import RenderError

BINARY = "gs"


def available() -> bool:
    return shutil.which(BINARY) is not None


def to_grayscale(pdf_bytes: bytes) -> bytes:
    """Convert a PDF to DeviceGray with Ghostscript; raise on failure."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.pdf"
        dst = Path(tmp) / "out.pdf"
        src.write_bytes(pdf_bytes)
        cmd = [
            BINARY,
            "-sDEVICE=pdfwrite",
            "-sProcessColorModel=DeviceGray",
            "-sColorConversionStrategy=Gray",
            "-dOverrideICC",
            "-dNOPAUSE",
            "-dBATCH",
            "-dQUIET",
            f"-sOutputFile={dst}",
            str(src),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
        if proc.returncode != 0 or not dst.exists():
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RenderError(f"ghostscript grayscale failed: {detail}")
        return dst.read_bytes()

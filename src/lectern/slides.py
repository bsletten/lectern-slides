"""Fence-aware slide splitting.

A slide break is a line that is *exactly* ``---`` (after stripping surrounding
whitespace) — but only when it is not inside a fenced code block (``` ``` ``` or
``~~~``). This is the other load-bearing pure function, so the fence bookkeeping
lives here and is shared with the include expander.

Slides are returned with their 1-based starting line number in the original
file, so errors and provenance comments can cite a real location.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A fence marker line: up to 3 leading spaces, then a run of >= 3 backticks or
# tildes, then an optional info string. Captures the run so we can match lengths.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


@dataclass(frozen=True)
class Fence:
    """An open code fence: its delimiter char and the run length that opened it."""

    char: str
    length: int


@dataclass
class Slide:
    """One slide's text and where it began in its source file."""

    text: str
    start_line: int  # 1-based line of the slide's first line in the source file


def fence_marker(line: str) -> Fence | None:
    """Return the :class:`Fence` a line would open/close, or ``None``."""
    m = _FENCE_RE.match(line)
    if not m:
        return None
    run = m.group(1)
    return Fence(char=run[0], length=len(run))


def fence_info(line: str) -> str:
    """The info string after a fence open — e.g. ``mermaid`` for a mermaid block."""
    m = _FENCE_RE.match(line)
    return m.group(2).strip() if m else ""


def closes_fence(line: str, open_fence: Fence) -> bool:
    """Whether *line* closes ``open_fence`` (same char, >= length, no info)."""
    marker = fence_marker(line)
    if marker is None or marker.char != open_fence.char:
        return False
    if marker.length < open_fence.length:
        return False
    # A closing fence carries no info string (only trailing whitespace allowed).
    _, info = _FENCE_RE.match(line).groups()
    return info.strip() == ""


def split_slides(text: str, start_line: int = 1) -> list[Slide]:
    """Split *text* into slides on bare ``---`` lines, ignoring fenced code.

    ``start_line`` is the 1-based line number of *text*'s first line within its
    file (so callers that stripped frontmatter can still report true locations).
    A file with no separators yields a single slide. ``---`` lines themselves are
    consumed (they are delimiters, not content).
    """
    slides: list[Slide] = []
    current: list[str] = []
    current_start = start_line
    fence: Fence | None = None

    for offset, line in enumerate(text.split("\n")):
        lineno = start_line + offset

        if fence is None:
            marker = fence_marker(line)
            if marker is not None:
                fence = marker
            elif line.strip() == "---":
                slides.append(Slide("\n".join(current), current_start))
                current = []
                current_start = lineno + 1
                continue
        else:
            if closes_fence(line, fence):
                fence = None

        current.append(line)

    slides.append(Slide("\n".join(current), current_start))
    return slides

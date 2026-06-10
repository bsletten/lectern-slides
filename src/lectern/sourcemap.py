"""Provenance primitives: where an assembled line came from.

The assemble stage produces a flat list of :class:`OutLine` (text + origin).
That stream is the assembled deck *and* its source-map: any later stage can ask
:meth:`SourceMap.at` which authored ``file:line`` produced output line *N*, so
errors discovered downstream still map back to the source the author wrote.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceLocation:
    """An authored location: a file, optionally a 1-based line within it."""

    file: str
    line: int | None = None

    def __str__(self) -> str:
        if self.line is not None:
            return f"{self.file}:{self.line}"
        return self.file


@dataclass
class OutLine:
    """One line of assembled output and the source location it came from.

    ``is_separator`` marks the synthetic ``---`` lines the assembler inserts
    between slides, so downstream stages can split into slides without having to
    re-run the fence-aware splitter over the assembled text.
    """

    text: str
    loc: SourceLocation
    is_separator: bool = False


@dataclass
class SourceMap:
    """Maps 1-based assembled-output line numbers back to source locations."""

    lines: list[SourceLocation]

    def at(self, lineno: int) -> SourceLocation | None:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1]
        return None

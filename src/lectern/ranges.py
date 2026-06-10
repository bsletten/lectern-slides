"""The ``#1-3,14`` slide-range grammar.

Pure, I/O-free, and heavily tested: this is one of the load-bearing functions
the spec calls out. Indices are 1-based slide positions within an included file.

Grammar (whitespace anywhere is ignored)::

    N        single slide
    A-B      inclusive range
    A-       slide A through the end
    -B       start through slide B
    a,b,c    comma-separated list of any of the above

Out-of-range and malformed specs raise :class:`~lectern.errors.RangeError`; the
caller decorates the error with the originating file/directive location.
"""

from __future__ import annotations

from .errors import RangeError


def parse_ranges(spec: str, total: int) -> list[int]:
    """Expand *spec* into an ordered list of 1-based slide indices.

    ``total`` is the number of slides in the target file; it bounds open-ended
    ranges (``A-``, ``-B``) and validates explicit indices. Order is preserved as
    written; duplicates from overlapping segments are kept (the author asked for
    them). Raises :class:`RangeError` on empty/malformed segments, reversed
    ranges, or any index outside ``1..total``.
    """
    if total < 0:
        raise ValueError("total must be non-negative")

    text = spec.strip()
    if not text:
        raise RangeError("empty range specification")

    result: list[int] = []
    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            raise RangeError(f"empty range segment in '{spec}'")

        if "-" in part:
            lo_text, _, hi_text = part.partition("-")
            lo = _parse_int(lo_text, part) if lo_text.strip() else 1
            hi = _parse_int(hi_text, part) if hi_text.strip() else total
            if lo > hi:
                raise RangeError(
                    f"reversed range '{part}' (start {lo} is after end {hi})"
                )
            for i in range(lo, hi + 1):
                _check_bounds(i, total)
                result.append(i)
        else:
            i = _parse_int(part, part)
            _check_bounds(i, total)
            result.append(i)

    return result


def _parse_int(text: str, part: str) -> int:
    token = text.strip()
    try:
        return int(token)
    except ValueError:
        raise RangeError(f"invalid number '{token}' in range '{part}'") from None


def _check_bounds(i: int, total: int) -> None:
    if i < 1 or i > total:
        plural = "slide" if total == 1 else "slides"
        raise RangeError(f"slide {i} is out of range (file has {total} {plural})")

"""Imposition geometry — pure layout math in PDF points (1pt = 1/72").

Given a layout preset, a sheet size, and margin/gutter lengths, this computes the
**cells** (slide rect + optional notes rect) in reading order, and fits each
vector master page into its cell preserving aspect. No pypdf, no I/O — just the
numbers the imposition step turns into ``Transformation().scale().translate()``.

PDF coordinates put the origin at the bottom-left, so row 0 (top of the page) has
the highest ``y``; callers don't need to know that — they just place the master at
the returned ``(x, y)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import ConfigError

# Named paper sizes in points (portrait).
_PAPER = {
    "letter": (612.0, 792.0),
    "a4": (595.28, 841.89),
    "legal": (612.0, 1008.0),
}

# layout -> (rows, cols, notes). Notes layouts are one slide per row with a notes
# column to its right; grids fill left-to-right, top-to-bottom.
_LAYOUTS = {
    "1up": (1, 1, False),
    "2up": (2, 1, False),
    "2x2": (2, 2, False),
    "6up": (3, 2, False),
    "2up-notes": (2, 1, True),
    "3up-notes": (3, 1, True),
}

# Fraction of the content width given to the slide thumbnail in a notes layout.
_NOTES_SLIDE_FRACTION = 0.58

_LENGTH = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(mm|cm|in|pt|px)?\s*$")
_DIMS = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*[xX]\s*([0-9]*\.?[0-9]+)\s*$")


@dataclass(frozen=True)
class Cell:
    """One slide slot on a sheet (bottom-left origin), plus an optional notes box."""

    x: float
    y: float
    width: float
    height: float
    notes: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class Placement:
    """A master page fitted (contain) into a cell: where to draw it, at what scale."""

    x: float
    y: float
    width: float
    height: float
    scale: float


def length_to_pt(value: str) -> float:
    """Parse a CSS-ish length (``12mm``, ``0.5in``, ``18pt``, ``24px``) to points."""
    m = _LENGTH.match(value)
    if not m:
        raise ConfigError(
            f"invalid length '{value}' (use e.g. '12mm', '0.5in', '18pt')"
        )
    n = float(m.group(1))
    unit = m.group(2) or "pt"
    factor = {"pt": 1.0, "px": 72 / 96, "in": 72.0, "mm": 72 / 25.4, "cm": 72 / 2.54}
    return n * factor[unit]


def per_page(layout: str) -> int:
    """How many slides one sheet of this layout holds."""
    rows, cols, _ = _LAYOUTS[layout]
    return rows * cols


def is_notes_layout(layout: str) -> bool:
    return _LAYOUTS[layout][2]


def sheet_size(
    paper: str, orientation: str, master: tuple[float, float]
) -> tuple[float, float]:
    """Resolve the sheet (W, H) in points for ``paper`` at ``orientation``.

    ``deck`` uses the master page size as-is; named sizes and ``WxH`` (CSS pixels)
    are oriented per ``orientation``. ``orientation="auto"`` matches the sheet to
    the deck (landscape for a wide master), so 16:9 slides tile without big gaps.
    """
    key = paper.strip().lower()
    if key == "deck":
        w, h = master
    elif key in _PAPER:
        w, h = _PAPER[key]
    else:
        dims = _DIMS.match(paper)
        if not dims:
            raise ConfigError(
                f"invalid [pdf] paper '{paper}' "
                "(use 'deck', 'letter', 'a4', or 'WxH' in pixels)"
            )
        # WxH is given in CSS pixels (like the deck aspect); convert to points.
        w, h = float(dims.group(1)) * 72 / 96, float(dims.group(2)) * 72 / 96

    want = orientation
    if want == "auto":
        want = "landscape" if master[0] >= master[1] else "portrait"
    if want == "landscape" and h > w:
        w, h = h, w
    elif want == "portrait" and w > h:
        w, h = h, w
    return w, h


def page_cells(
    layout: str, sheet: tuple[float, float], margin: float, gutter: float
) -> list[Cell]:
    """The slide cells for one sheet, in reading order (top-left first)."""
    rows, cols, notes = _LAYOUTS[layout]
    sw, sh = sheet

    if layout == "1up":
        # Full-bleed: the whole sheet is the cell (clean projection slides).
        return [Cell(0.0, 0.0, sw, sh)]

    content_w = sw - 2 * margin
    content_h = sh - 2 * margin
    row_h = (content_h - (rows - 1) * gutter) / rows

    cells: list[Cell] = []
    if notes:
        slide_w = content_w * _NOTES_SLIDE_FRACTION
        notes_w = content_w - slide_w - gutter
        for r in range(rows):
            y = margin + (rows - 1 - r) * (row_h + gutter)
            cells.append(
                Cell(
                    margin,
                    y,
                    slide_w,
                    row_h,
                    notes=(margin + slide_w + gutter, y, notes_w, row_h),
                )
            )
    else:
        cell_w = (content_w - (cols - 1) * gutter) / cols
        for r in range(rows):
            y = margin + (rows - 1 - r) * (row_h + gutter)
            for c in range(cols):
                x = margin + c * (cell_w + gutter)
                cells.append(Cell(x, y, cell_w, row_h))
    return cells


def fit_contain(cell: Cell, master_w: float, master_h: float) -> Placement:
    """Fit a master page into ``cell`` preserving aspect, centered."""
    scale = min(cell.width / master_w, cell.height / master_h)
    w = master_w * scale
    h = master_h * scale
    x = cell.x + (cell.width - w) / 2
    y = cell.y + (cell.height - h) / 2
    return Placement(x=x, y=y, width=w, height=h, scale=scale)

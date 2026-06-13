"""Imposition: place the vector master pages onto sheets, draw the chrome.

pypdf scales and translates each *vector* master page into its grid cell (no
rasterizing — slides stay crisp and text selectable). The chrome pypdf can't draw
— hairline frames, slide numbers, header/footer, and the **notes text** beside
each thumbnail in a handout layout — is a thin reportlab overlay merged on top.
Both libraries are pure-Python and BSD-licensed, so the tool stays MIT-clean.

Geometry (cells, fit-contain) comes from :mod:`lectern.pdf.geometry`; this module
is the part that actually touches pypdf/reportlab, imported lazily.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from . import geometry

if TYPE_CHECKING:
    from .options import PdfOptions

_NOTES_FONT = "Helvetica"
_NOTES_SIZE = 8.5
_CHROME_FONT = "Helvetica"
_CHROME_SIZE = 8.0
_PAD = 6.0  # inner padding inside a notes box / frame, in points


def _wrap(text: str, font: str, size: float, max_w: float) -> list[str]:
    """Greedy word-wrap ``text`` to ``max_w`` points (reportlab metrics)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            if stringWidth(f"{cur} {w}", font, size) <= max_w:
                cur = f"{cur} {w}"
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _expand(template: str, *, title: str, date: str, page: int, pages: int) -> str:
    return (
        template.replace("{title}", title)
        .replace("{date}", date)
        .replace("{page}", str(page))
        .replace("{pages}", str(pages))
    )


def _draw_overlay(
    sheet: tuple[float, float],
    placements: list[tuple[geometry.Placement, geometry.Cell, int, list[str]]],
    *,
    options: PdfOptions,
    header: str,
    footer: str,
):
    """Build a one-page reportlab overlay (frames, numbers, notes, header/footer)."""
    from reportlab.pdfgen import canvas

    sw, sh = sheet
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(sw, sh))
    c.setLineWidth(0.5)

    for placement, cell, number, notes in placements:
        if options.frame and options.layout != "1up":
            c.setStrokeGray(0.7)
            c.rect(placement.x, placement.y, placement.width, placement.height)
        if options.slide_numbers and options.layout != "1up":
            c.setFillGray(0.45)
            c.setFont(_CHROME_FONT, _CHROME_SIZE)
            c.drawString(placement.x + 2, placement.y - _CHROME_SIZE - 1, str(number))
        if cell.notes is not None and notes:
            nx, ny, nw, nh = cell.notes
            c.setFillGray(0.1)
            text = "\n".join(notes)
            lines: list[str] = []
            for ln in _wrap(text, _NOTES_FONT, _NOTES_SIZE, nw - 2 * _PAD):
                lines.append(ln)
            leading = _NOTES_SIZE * 1.3
            ty = ny + nh - _PAD - _NOTES_SIZE
            c.setFont(_NOTES_FONT, _NOTES_SIZE)
            for ln in lines:
                if ty < ny + _PAD:
                    break  # clip overflow rather than spill into the next row
                c.drawString(nx + _PAD, ty, ln)
                ty -= leading

    if header or footer:
        c.setFillGray(0.4)
        c.setFont(_CHROME_FONT, _CHROME_SIZE)
        if header:
            c.drawCentredString(sw / 2, sh - 18, header)
        if footer:
            c.drawCentredString(sw / 2, 12, footer)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def impose(
    master_pdf: bytes,
    *,
    options: PdfOptions,
    notes: list[list[str]],
    title: str,
    date: str,
) -> bytes:
    """Impose the master onto sheets per ``options.layout``; return PDF bytes."""
    from pypdf import PdfReader, PdfWriter, Transformation

    reader = PdfReader(io.BytesIO(master_pdf))
    src_pages = reader.pages
    n = len(src_pages)
    master_size = (
        float(src_pages[0].mediabox.width),
        float(src_pages[0].mediabox.height),
    )

    # 1up on deck paper is the master verbatim — the cheap, clean projection case.
    # Return the master bytes unchanged: a PdfWriter round-trip would rebuild the
    # catalog and drop the tagged structure tree (/MarkInfo, /StructTreeRoot,
    # /Lang). Verbatim passthrough preserves them — the whole point of `tagged`.
    if options.layout == "1up" and options.paper.strip().lower() == "deck":
        return master_pdf

    orientation = options.orientation
    if orientation == "auto":
        orientation = geometry.auto_orientation(options.layout, master_size)
    sheet = geometry.sheet_size(options.paper, orientation, master_size)
    margin = geometry.length_to_pt(options.margins)
    gutter = geometry.length_to_pt(options.gutter)
    cells = geometry.page_cells(options.layout, sheet, margin, gutter)
    slots = len(cells)
    pages_total = (n + slots - 1) // slots

    writer = PdfWriter()
    for sheet_idx in range(pages_total):
        blank = writer.add_blank_page(width=sheet[0], height=sheet[1])
        placements: list[tuple[geometry.Placement, geometry.Cell, int, list[str]]] = []
        for slot, cell in enumerate(cells):
            page_idx = sheet_idx * slots + slot
            if page_idx >= n:
                break
            src = src_pages[page_idx]
            mw, mh = float(src.mediabox.width), float(src.mediabox.height)
            place = geometry.fit_contain(cell, mw, mh)
            blank.merge_transformed_page(
                src,
                Transformation().scale(place.scale).translate(place.x, place.y),
            )
            slide_notes = notes[page_idx] if page_idx < len(notes) else []
            placements.append((place, cell, page_idx + 1, slide_notes))

        overlay = _draw_overlay(
            sheet,
            placements,
            options=options,
            header=_expand(
                options.header,
                title=title,
                date=date,
                page=sheet_idx + 1,
                pages=pages_total,
            ),
            footer=_expand(
                options.footer,
                title=title,
                date=date,
                page=sheet_idx + 1,
                pages=pages_total,
            ),
        )
        blank.merge_page(PdfReader(overlay).pages[0])

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()

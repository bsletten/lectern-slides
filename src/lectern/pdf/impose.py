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
import re
from typing import TYPE_CHECKING

from . import geometry

if TYPE_CHECKING:
    from .options import PdfOptions

_NOTES_FONT = "Helvetica"
_NOTES_SIZE = 8.5
_CHROME_FONT = "Helvetica"
_CHROME_SIZE = 8.0
_PAD = 6.0  # inner padding inside a notes box / frame, in points

# CJK ranges: CJK symbols/punctuation, Hiragana, Katakana, CJK Ext-A, CJK
# Unified, compatibility ideographs, Hangul syllables, fullwidth forms. The base
# 14 PDF fonts (Helvetica et al.) carry none of these, so CJK notes drawn in
# Helvetica come out as tofu/black boxes — hence the script-aware font below.
_CJK_RE = re.compile("[　-〿぀-ゟ゠-ヿ㐀-䶿一-鿿가-힯豈-﫿＀-￯]")
_KANA_RE = re.compile("[぀-ゟ゠-ヿ]")  # Hiragana / Katakana
_HANGUL_RE = re.compile("[가-힯]")

# reportlab's built-in CID fonts reference Adobe's standard Asian font
# collection, so CJK text renders in mainstream viewers (Preview, Acrobat,
# Chrome) WITHOUT embedding or bundling a multi-megabyte font — which would
# break the "keep the core dependency-light" directive. (System CJK fonts like
# Hiragino/PingFang/Noto are CFF-outline and reportlab can't embed them anyway.)
# One font per script; the chosen one covers Latin too, so mixed notes are fine.
_CID_FONTS = {
    "jp": "HeiseiKakuGo-W5",  # Adobe-Japan1
    "kr": "HYGothic-Medium",  # Adobe-Korea1
    "sc": "STSong-Light",  # Adobe-GB1 (Simplified)
    "tc": "MSung-Light",  # Adobe-CNS1 (Traditional)
}
_cjk_registered: set[str] = set()


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _script_for_lang(lang: str | None) -> str | None:
    """Map a BCP-47 ``lang`` to a CJK script key, or ``None`` if it isn't CJK.
    The author's declared document language disambiguates Han text that the
    content heuristic can't (Japanese kanji vs Chinese share code points)."""
    if not lang:
        return None
    tag = lang.lower()
    if tag.startswith("ja"):
        return "jp"
    if tag.startswith("ko"):
        return "kr"
    if tag.startswith("zh"):
        # zh-Hant / zh-TW / zh-HK ⇒ Traditional; otherwise Simplified.
        return "tc" if ("hant" in tag or "-tw" in tag or "-hk" in tag) else "sc"
    return None


def _cjk_font(*texts: str, lang: str | None = None) -> str | None:
    """Pick + register a CID font for the script in *texts*, or ``None`` if they
    hold no CJK. Priority: an explicit CJK ``lang`` ⇒ kana ⇒ Hangul ⇒ default
    Japanese (Adobe-Japan1 has the broadest kanji coverage, and Han-only text is
    usually a few Japanese terms in a Western deck). Registered once and cached;
    a registration failure degrades to ``None`` (Helvetica)."""
    joined = "\n".join(texts)
    if not _has_cjk(joined):
        return None
    script = _script_for_lang(lang)
    if script is None:
        if _KANA_RE.search(joined):
            script = "jp"
        elif _HANGUL_RE.search(joined):
            script = "kr"
        else:
            script = "jp"
    name = _CID_FONTS[script]
    if name not in _cjk_registered:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        try:
            pdfmetrics.registerFont(UnicodeCIDFont(name))
        except Exception:  # pragma: no cover - reportlab ships these fonts
            return None
        _cjk_registered.add(name)
    return name


def _atoms(s: str):
    """Break-point atoms for wrapping: whitespace-delimited words, single CJK
    characters (which may break anywhere), and single spaces."""
    buf = ""
    for ch in s:
        if ch == " ":
            if buf:
                yield buf
                buf = ""
            yield " "
        elif _CJK_RE.match(ch):
            if buf:
                yield buf
                buf = ""
            yield ch
        else:
            buf += ch
    if buf:
        yield buf


def _reflow(notes: list[str]) -> str:
    """Join the note's soft-wrapped source lines into paragraphs so the handout
    fills the notes column instead of echoing the author's hard wraps.

    Markdown semantics: a single newline is a space, a blank line separates
    paragraphs — the same way the on-screen speaker notes render, so the printed
    handout matches. The result is paragraphs joined by a blank line; the wrapper
    then breaks each to the column width."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in notes:
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def _wrap(text: str, font: str, size: float, max_w: float) -> list[str]:
    """Greedy-wrap ``text`` to ``max_w`` points (reportlab metrics). Latin wraps
    on whitespace; CJK — which has no spaces — breaks between characters so a long
    run doesn't overflow the narrow notes column. Blank lines (paragraph breaks
    from :func:`_reflow`) pass through as empty output lines."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for atom in _atoms(paragraph):
            if atom == " " and not line:
                continue  # no leading space on a fresh line
            candidate = line + atom
            if not line or stringWidth(candidate, font, size) <= max_w:
                line = candidate
            else:
                lines.append(line.rstrip(" "))
                line = "" if atom == " " else atom
        lines.append(line.rstrip(" "))
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
    cjk_font: str | None = None,
):
    """Build a one-page reportlab overlay (frames, numbers, notes, header/footer).

    ``cjk_font`` (resolved once per document) is used for any string that holds
    CJK, so Kanji/kana/Hangul render instead of tofu; Latin-only strings keep
    Helvetica."""
    from reportlab.pdfgen import canvas

    def font_for(text: str, base: str) -> str:
        """The CJK font when *text* needs it, else the Latin *base* font."""
        return cjk_font if (cjk_font and _has_cjk(text)) else base

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
            text = _reflow(notes)
            font = font_for(text, _NOTES_FONT)
            lines = _wrap(text, font, _NOTES_SIZE, nw - 2 * _PAD)
            leading = _NOTES_SIZE * 1.3
            ty = ny + nh - _PAD - _NOTES_SIZE
            c.setFont(font, _NOTES_SIZE)
            for ln in lines:
                if ty < ny + _PAD:
                    break  # clip overflow rather than spill into the next row
                c.drawString(nx + _PAD, ty, ln)
                ty -= leading

    if header or footer:
        c.setFillGray(0.4)
        if header:
            c.setFont(font_for(header, _CHROME_FONT), _CHROME_SIZE)
            c.drawCentredString(sw / 2, sh - 18, header)
        if footer:
            c.setFont(font_for(footer, _CHROME_FONT), _CHROME_SIZE)
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
    lang: str | None = None,
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

    # Resolve one CJK font for the whole document (notes + header/footer + title),
    # so Kanji/kana/Hangul in any of them render instead of tofu. None ⇒ no CJK.
    cjk_font = _cjk_font(
        *("\n".join(note) for note in notes),
        title,
        options.header,
        options.footer,
        lang=lang,
    )

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
            cjk_font=cjk_font,
        )
        blank.merge_page(PdfReader(overlay).pages[0])

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()

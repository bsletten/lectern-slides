"""Authoring-time accessibility checks, surfaced by ``lectern check``.

Like every Lectern diagnostic these are **source-cited** — each warning names the
``file:line`` (or theme) the author can act on. The checks are intentionally
small and high-signal, the ones that genuinely break a screen-reader experience:

* a slide with no accessible **name** — neither a heading nor a ``label`` /
  ``aria-label`` (so image- and quotation-only slides just add a ``label``);
* an ``<iframe>`` embed with no ``title=``;
* a raw HTML ``<img>`` with no ``alt`` attribute at all;
* a ```` ```mermaid ```` diagram with no ``accTitle`` / ``accDescr`` (Mermaid
  renders those to the SVG's ``<title>``/``<desc>`` + ``aria-labelledby``);
* a Font Awesome icon (``<i>``/``<span class="fa-…">``) with neither
  ``aria-hidden="true"`` (decorative) nor an accessible name (``aria-label`` /
  ``title``) — otherwise a screen reader announces nothing or garbage;
* a theme whose text tokens fall below WCAG AA contrast (4.5:1), or whose
  ``--accent`` (a graphical element) falls below WCAG non-text contrast (3:1).

Only *raw* ``<img>`` (HTML passthrough) is linted for alt. Markdown ``![](src)``
is left alone — an empty alt there is the author's explicit "decorative"
declaration, not a mistake; ``alt=""`` says the same on a raw ``<img>``.
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING

from .render.lowering import is_blank_group, parse_tokens
from .slides import closes_fence, fence_info, fence_marker

if TYPE_CHECKING:
    from .preprocess import AssembledDeck

_PROVENANCE = "<!-- @from "
# Inline code spans (`…`, ``…``) — stripped before tag scanning so an `<img>` or
# `<i class="fa-…">` *shown as code* in a slide isn't mistaken for a real one.
_INLINE_CODE = re.compile(r"(`+)(?:.*?)\1")
# HTML/XML comments (possibly multi-line) — blanked before tag scanning so a tag
# named inside a comment (e.g. an inlined SVG's notes) isn't mistaken for markup.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING = re.compile(r"^\s*#{1,6}\s+\S")
_RAW_HEADING = re.compile(r"<h[1-6][\s/>]", re.IGNORECASE)
_SLIDE_DIRECTIVE = re.compile(r"^\s*<!--\s*slide:\s*(.+?)\s*-->\s*$")
# Mermaid's accessibility directives (case-sensitive), single-line or block form.
_ACC = re.compile(r"^\s*acc(?:Title|Descr)\b")


def audit(deck: AssembledDeck) -> list[str]:
    """Return source-cited accessibility warnings for the assembled deck."""
    warnings: list[str] = []
    number = 0
    for group in deck.slides():
        if is_blank_group(group):
            continue
        number += 1
        warnings.extend(_slide_warnings(number, group))
    warnings.extend(_theme_warnings(deck))
    return warnings


def _strip_inline_code(text: str) -> str:
    """Blank out inline-code spans so a tag shown as code isn't scanned as real."""
    return _INLINE_CODE.sub(" ", text)


def _blank_html_comments(group):
    """Return the slide's lines with HTML-comment regions blanked.

    A comment can span lines (an inlined SVG's documentation block, say), and its
    prose may mention a tag — ``a plain <img src> …`` — which is not real markup.
    Blank every ``<!-- … -->`` region, preserving newlines so each line keeps its
    1:1 mapping back to its :class:`OutLine` (location/separator unchanged), then
    the tag scanners run over the cleaned copy.
    """
    joined = "\n".join(o.text for o in group)

    def _keep_newlines(m: re.Match) -> str:
        return "".join("\n" if c == "\n" else " " for c in m.group(0))

    blanked = _HTML_COMMENT.sub(_keep_newlines, joined).split("\n")
    return [dataclasses.replace(o, text=t) for o, t in zip(group, blanked, strict=True)]


def _has_heading(group) -> bool:
    """Whether the slide has a heading (ATX or raw ``<hN>``), fence-aware."""
    fence = None
    for outline in group:
        text = outline.text
        if fence is not None:
            if closes_fence(text, fence):
                fence = None
            continue
        marker = fence_marker(text)
        if marker is not None:
            fence = marker
            continue
        if _HEADING.match(text) or _RAW_HEADING.search(text):
            return True
    return False


def _has_label(group) -> bool:
    """Whether a slide directive supplies a ``label`` / ``aria-label``."""
    for outline in group:
        m = _SLIDE_DIRECTIVE.match(outline.text)
        if m:
            _classes, _ident, attrs = parse_tokens(m.group(1))
            if "label" in attrs or "aria-label" in attrs:
                return True
    return False


def _slide_warnings(number: int, group) -> list[str]:
    lines = [o for o in group if not o.is_separator]
    cite = next(
        (o.loc for o in lines if o.text.strip() and not o.text.startswith(_PROVENANCE)),
        lines[0].loc if lines else None,
    )
    out: list[str] = []

    if not _has_heading(group) and not _has_label(group):
        out.append(
            f"{cite}: slide {number} has no heading or label — add a heading or "
            '`<!-- slide: label="…" -->` so screen readers can identify it'
        )

    # Scan tags over a comment-blanked copy: a tag named inside a comment (e.g. an
    # inlined SVG's documentation) is prose, not markup.
    scan = _blank_html_comments(group)
    for loc in _tags_missing_attr(scan, "iframe", "title"):
        out.append(
            f"{loc}: an <iframe> embed has no title= — add one so the embed has "
            "an accessible name"
        )
    # Raw HTML `<img>` (passthrough) with no `alt` at all. Markdown `![](src)` is
    # left alone — empty alt there is the author's intentional "decorative".
    for loc in _tags_missing_attr(scan, "img", "alt"):
        out.append(
            f'{loc}: a raw <img> has no alt= — add alt text (use alt="" if it is '
            "purely decorative)"
        )

    for loc in _font_awesome_warnings(scan):
        out.append(
            f"{loc}: a Font Awesome icon has no aria-hidden or accessible name — "
            'add aria-hidden="true" if decorative, or aria-label="…"'
        )

    out.extend(_mermaid_warnings(group))
    return out


_OPEN = {tag: re.compile(rf"<{tag}\b", re.IGNORECASE) for tag in ("iframe", "img")}

# A Font Awesome icon element, its class value, an `fa-…` token, and the markers
# that make it accessible (decorative or named).
_FA_TAG = re.compile(r"<(?:i|span)\b[^>]*>", re.IGNORECASE)
_FA_CLASS = re.compile(r"""class\s*=\s*("|')(.*?)\1""", re.IGNORECASE)
_FA_TOKEN = re.compile(r"(?<![\w-])fa-[\w-]+")
_FA_OK = re.compile(
    r"""aria-hidden\s*=\s*["']?\s*true"""  # decorative
    r"|aria-label\s*="  # named
    r"|\btitle\s*=",
    re.IGNORECASE,
)


def _font_awesome_warnings(group) -> list[str]:
    """Locs of Font Awesome icons (outside code fences) that are neither marked
    decorative (``aria-hidden="true"``) nor named (``aria-label``/``title``)."""
    out: list[str] = []
    fence = None
    for outline in group:
        text = outline.text
        if fence is not None:
            if closes_fence(text, fence):
                fence = None
            continue
        marker = fence_marker(text)
        if marker is not None:
            fence = marker
            continue
        for m in _FA_TAG.finditer(_strip_inline_code(text)):
            tag = m.group(0)
            cls = _FA_CLASS.search(tag)
            if cls and _FA_TOKEN.search(cls.group(2)) and not _FA_OK.search(tag):
                out.append(str(outline.loc))
                break  # one warning per line is enough
    return out


def _tags_missing_attr(group, tag: str, attr: str) -> list[str]:
    """Locs of raw ``<tag …>`` (outside code fences) with no ``attr=``.

    Fence-aware, so a tag shown *inside* a code sample isn't flagged; opening
    tags may wrap across lines, so we gather to the closing ``>``.
    """
    lines = [o for o in group if not o.is_separator]
    has_attr = re.compile(rf"\b{attr}\s*=", re.IGNORECASE)
    out: list[str] = []
    fence = None
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i].text
        if fence is not None:
            if closes_fence(raw, fence):
                fence = None
            i += 1
            continue
        marker = fence_marker(raw)
        if marker is not None:
            fence = marker
            i += 1
            continue
        text = _strip_inline_code(raw)  # don't scan tags shown as inline code
        if _OPEN[tag].search(text):
            loc, gathered, j = lines[i].loc, text, i
            while ">" not in gathered and j + 1 < n:
                j += 1
                gathered += " " + _strip_inline_code(lines[j].text)
            if not has_attr.search(gathered):
                out.append(str(loc))
            i = j
        i += 1
    return out


def _mermaid_warnings(group) -> list[str]:
    """A ```mermaid diagram with no accTitle/accDescr has no text alternative."""
    out: list[str] = []
    fence = None
    open_loc = None
    is_mermaid = False
    described = False
    for outline in group:
        text = outline.text
        if fence is not None:
            if closes_fence(text, fence):
                if is_mermaid and not described:
                    out.append(
                        f"{open_loc}: a mermaid diagram has no accTitle/accDescr — "
                        "add one (e.g. `accDescr: …` inside the diagram) so screen "
                        "readers get a text alternative"
                    )
                fence = None
                is_mermaid = False
                described = False
            elif _ACC.match(text):
                described = True
            continue
        marker = fence_marker(text)
        if marker is not None:
            fence = marker
            open_loc = outline.loc
            is_mermaid = fence_info(text).split(" ")[0].lower() == "mermaid"
            described = False
    return out


def _theme_warnings(deck: AssembledDeck) -> list[str]:
    from .pdf.colors import contrast, parse_root_tokens
    from .theming import resolve_theme_css

    try:
        name, css = resolve_theme_css(deck.config.theme, deck.root)
    except Exception:
        return []  # a bad theme path is reported elsewhere
    tokens = parse_root_tokens(css)

    out: list[str] = []
    # (fg token, bg token, min ratio, what). Text pairs use AA 4.5:1; the accent
    # is a graphical element (rules, list markers, mermaid diagram lines/borders)
    # held to WCAG non-text 3:1.
    checks = (
        ("--fg", "--bg", 4.5, "body text"),
        ("--inverse-fg", "--inverse-bg", 4.5, "inverse text"),
        ("--accent", "--bg", 3.0, "accent (rules, markers, diagram lines)"),
    )
    for fg, bg, minimum, what in checks:
        if fg in tokens and bg in tokens:
            ratio = contrast(tokens[fg], tokens[bg])
            if ratio is not None and ratio < minimum:
                standard = "WCAG AA" if minimum >= 4.5 else "WCAG non-text"
                out.append(
                    f"theme '{name}': {what} ({tokens[fg]} on {tokens[bg]}) is "
                    f"{ratio:.1f}:1, below {standard} ({minimum:g}:1)"
                )
    return out

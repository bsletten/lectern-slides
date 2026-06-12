"""Authoring-time accessibility checks, surfaced by ``lectern check``.

Like every Lectern diagnostic these are **source-cited** — each warning names the
``file:line`` (or theme) the author can act on. The checks are intentionally
small and high-signal, the ones that genuinely break a screen-reader experience:

* a slide with no accessible **name** — neither a heading nor a ``label`` /
  ``aria-label`` (so image- and quotation-only slides just add a ``label``);
* an ``<iframe>`` embed with no ``title=``;
* a theme whose primary text/background tokens fall below WCAG AA contrast.

Markdown image *alt* is deliberately not linted: ``![](src)`` is the author's
explicit "decorative" declaration, not a mistake.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .render.lowering import is_blank_group, parse_tokens
from .slides import closes_fence, fence_marker

if TYPE_CHECKING:
    from .preprocess import AssembledDeck

_PROVENANCE = "<!-- @from "
_HEADING = re.compile(r"^\s*#{1,6}\s+\S")
_RAW_HEADING = re.compile(r"<h[1-6][\s/>]", re.IGNORECASE)
_SLIDE_DIRECTIVE = re.compile(r"^\s*<!--\s*slide:\s*(.+?)\s*-->\s*$")


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

    # `<iframe>` opening tags may wrap across lines; gather to the closing `>`.
    i, n = 0, len(lines)
    while i < n:
        if "<iframe" in lines[i].text.lower():
            loc, tag, j = lines[i].loc, lines[i].text, i
            while ">" not in tag and j + 1 < n:
                j += 1
                tag += " " + lines[j].text
            if "title=" not in tag.lower():
                out.append(
                    f"{loc}: an <iframe> embed has no title= — add one so the "
                    "embed has an accessible name"
                )
            i = j
        i += 1
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
    for fg, bg, what in (
        ("--fg", "--bg", "body text"),
        ("--inverse-fg", "--inverse-bg", "inverse text"),
    ):
        if fg in tokens and bg in tokens:
            ratio = contrast(tokens[fg], tokens[bg])
            if ratio is not None and ratio < 4.5:
                out.append(
                    f"theme '{name}': {what} ({tokens[fg]} on {tokens[bg]}) is "
                    f"{ratio:.1f}:1, below WCAG AA (4.5:1)"
                )
    return out

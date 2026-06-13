"""Linear, heading-structured Markdown export — ``lectern build -f outline``.

A plain reading view of the deck, independent of any render framework: one
section per slide (its own heading, or one synthesized from the slide ``label``),
the slide's prose body with Lectern directives and ``[text]{.cls}`` /
``::: {.cls}`` attribute syntax stripped, and the speaker notes rendered as prose.
A screen-reader transcript, an SEO/no-JS fallback, or a hand-off document.

Non-prose embeds collapse to their accessible name: a Mermaid diagram to its
``accTitle``/``accDescr``, an ``<iframe>`` to its ``title``. Author HTML comments
are dropped (but ``<!-- … -->`` shown inside ``code`` spans is preserved).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .render.lowering import is_blank_group, parse_div, parse_tokens
from .slides import closes_fence, fence_info, fence_marker

if TYPE_CHECKING:
    from .preprocess import AssembledDeck

_PROVENANCE = "<!-- @from "
_SLIDE_DIRECTIVE = re.compile(r"^\s*<!--\s*slide:\s*(.+?)\s*-->\s*$")
_NOTES_OPEN = re.compile(r"^\s*<!--\s*notes\s*-->\s*$")
_NOTES_CLOSE = re.compile(r"^\s*<!--\s*/notes\s*-->\s*$")
_FENCE_DIV = re.compile(r"^(:::+)\s*(.*?)\s*$")
_INLINE_SPAN = re.compile(r"\[([^\]]+)\]\{[^}]*\}")
_INLINE_CODE = re.compile(r"`+[^`]*`+")
_HEADING = re.compile(r"^\s*#{1,6}\s+(.*?)\s*#*\s*$")
_ACC = re.compile(r"^\s*acc(?:Title|Descr)\s*[:{]?\s*(.*?)\s*}?\s*$")
_IFRAME_TITLE = re.compile(r"""title\s*=\s*["']([^"']*)["']""", re.IGNORECASE)


def _clean(line: str) -> str:
    """Unwrap inline ``[text]{.cls}`` spans to their text."""
    return _INLINE_SPAN.sub(r"\1", line)


def _strip_inline_comments(line: str) -> tuple[str, bool]:
    """Strip ``<!-- … -->`` *outside* inline ``code`` spans.

    Returns ``(cleaned, opens_multiline)`` — the latter true if an unterminated
    ``<!--`` (a multi-line comment) opened. ``code`` spans are stashed first so a
    literal ``<!-- … -->`` written as an example isn't treated as a comment.
    """
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append(m.group(0))
        return f"\x00{len(codes) - 1}\x00"

    masked = _INLINE_CODE.sub(stash, line)
    masked = re.sub(r"<!--.*?-->", "", masked)
    opens = False
    if "<!--" in masked:
        masked = masked.split("<!--", 1)[0]
        opens = True
    masked = re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], masked)
    return masked, opens


def _iframe_line(lines: list[str]) -> str:
    """Collapse an ``<iframe>`` to a blockquote of its ``title`` (its a11y name)."""
    m = _IFRAME_TITLE.search(" ".join(lines))
    name = m.group(1).strip() if m else ""
    return f"> {name}" if name else "> _(embedded view)_"


def _slide_parts(group) -> tuple[list[str], list[str], str | None]:
    """Split one slide into (body lines, notes lines, label) as clean Markdown."""
    body: list[str] = []
    notes: list[str] = []
    label: str | None = None
    fence = None
    mermaid = False
    macc: list[str] = []
    iframe: list[str] | None = None
    in_notes_comment = False
    in_comment = False  # generic multi-line <!-- ... --> author annotation
    div_stack: list[str] = []
    directive_seen = False

    def in_notes() -> bool:
        return in_notes_comment or (bool(div_stack) and div_stack[-1] == "notes")

    def sink() -> list[str]:
        return notes if in_notes() else body

    for outline in group:
        line = outline.text
        if line.startswith(_PROVENANCE):
            continue

        if fence is not None:
            if mermaid:
                m = _ACC.match(line)
                if m and m.group(1).strip():
                    macc.append(m.group(1).strip())
                if closes_fence(line, fence):
                    sink().append(f"> {' — '.join(macc) if macc else '_(diagram)_'}")
                    fence, mermaid, macc = None, False, []
                continue
            sink().append(line)
            if closes_fence(line, fence):
                fence = None
            continue

        if iframe is not None:  # gather a (possibly multi-line) <iframe> tag
            iframe.append(line)
            if "</iframe>" in line or line.rstrip().endswith("/>"):
                sink().append(_iframe_line(iframe))
                iframe = None
            continue

        if in_comment:  # tail of a multi-line author comment
            idx = line.find("-->")
            if idx == -1:
                continue
            in_comment = False
            line = line[idx + 3 :]
            if not line.strip():
                continue
            # else: process the remainder of the line below

        if in_notes_comment:
            if _NOTES_CLOSE.match(line):
                in_notes_comment = False
            else:
                notes.append(_clean(line))
            continue

        fenced_div = _FENCE_DIV.match(line)
        if fenced_div and fenced_div.group(2) == "":  # closing :::
            if div_stack:
                div_stack.pop()
            continue
        if _NOTES_OPEN.match(line):
            in_notes_comment = True
            continue
        if not directive_seen:
            directive = _SLIDE_DIRECTIVE.match(line)
            if directive is not None:
                _classes, _ident, attrs = parse_tokens(directive.group(1))
                label = attrs.get("label") or attrs.get("aria-label")
                directive_seen = True
                continue
        if fenced_div is not None:  # opening ::: {.cls} — drop wrapper, keep content
            classes, _ident, _attrs = parse_div(fenced_div.group(2))
            div_stack.append("notes" if classes == ["notes"] else "div")
            continue

        marker = fence_marker(line)
        if marker is not None:
            fence = marker
            mermaid = fence_info(line).split(" ")[0].lower() == "mermaid"
            if not mermaid:
                sink().append(line)
            continue

        if "<iframe" in line:  # collapse raw embeds to their accessible name
            iframe = [line]
            if "</iframe>" in line or line.rstrip().endswith("/>"):
                sink().append(_iframe_line(iframe))
                iframe = None
            continue

        # Generic author comments (slide/notes/@from forms handled above); drop
        # them, but keep `<!-- … -->` shown inside an inline code span.
        if "<!--" in line:
            line, in_comment = _strip_inline_comments(line)
            if not line.strip():
                continue

        sink().append(_clean(line))

    return body, notes, label


def _leading_heading(body: list[str]) -> str | None:
    """The text of the slide's leading heading, or ``None`` if it has none."""
    for line in body:
        if line.strip():
            m = _HEADING.match(line)
            return m.group(1).strip() if m else None
    return None


def _without_leading_heading(body: list[str]) -> list[str]:
    for i, line in enumerate(body):
        if line.strip():
            return body[i + 1 :]
    return body


def build_outline(deck: AssembledDeck, config) -> str:
    """Render the assembled deck as a linear, heading-structured Markdown outline."""
    title = (config.title or "").strip() or "Deck"
    blocks: list[str] = [f"# {title}"]
    if (config.author or "").strip():
        blocks.append(f"_{config.author.strip()}_")

    number = 0
    first = True
    for group in deck.slides():
        if is_blank_group(group):
            continue
        number += 1
        body, notes, label = _slide_parts(group)

        lead = _leading_heading(body)
        if first and lead is not None and lead == title:
            # The title slide repeats the deck title — the document `# title`
            # already names it, so drop the duplicate leading heading.
            body = _without_leading_heading(body)
        elif lead is None:
            blocks.append(f"## {(label or f'Slide {number}').strip()}")
        first = False

        body_md = "\n".join(body).strip("\n")
        if body_md.strip():
            blocks.append(body_md)

        notes_md = "\n".join(notes).strip("\n")
        if notes_md.strip():
            quoted = "\n".join(
                f"> {ln}" if ln.strip() else ">" for ln in notes_md.split("\n")
            )
            blocks.append(f"**Notes**\n\n{quoted}")

    return "\n\n".join(b for b in blocks if b.strip()) + "\n"

"""Linear, heading-structured Markdown export — ``lectern build -f outline``.

A plain reading view of the deck, independent of any render framework: one
section per slide (its own heading, or one synthesized from the slide ``label``),
the slide's prose body with Lectern directives and ``[text]{.cls}`` /
``::: {.cls}`` attribute syntax stripped, and the speaker notes rendered as prose.
A screen-reader transcript, an SEO/no-JS fallback, or a hand-off document.

Mermaid diagrams (not prose) collapse to their ``accDescr``/``accTitle`` text —
the accessible description the audit nudges authors to write — or a placeholder.
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
_HEADING = re.compile(r"^\s*#{1,6}\s+\S")
_ACC = re.compile(r"^\s*acc(?:Title|Descr)\s*[:{]?\s*(.*?)\s*}?\s*$")


def _clean(line: str) -> str:
    """Unwrap inline ``[text]{.cls}`` spans to their text."""
    return _INLINE_SPAN.sub(r"\1", line)


def _slide_parts(group) -> tuple[list[str], list[str], str | None]:
    """Split one slide into (body lines, notes lines, label) as clean Markdown."""
    body: list[str] = []
    notes: list[str] = []
    label: str | None = None
    fence = None
    mermaid = False
    macc: list[str] = []
    in_notes_comment = False
    in_comment = False  # generic multi-line <!-- ... --> author annotation
    div_stack: list[str] = []
    directive_seen = False

    def in_notes() -> bool:
        return in_notes_comment or (bool(div_stack) and div_stack[-1] == "notes")

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
                    desc = " ".join(macc) if macc else "_(diagram)_"
                    (notes if in_notes() else body).append(f"> {desc}")
                    fence, mermaid, macc = None, False, []
                continue
            (notes if in_notes() else body).append(line)
            if closes_fence(line, fence):
                fence = None
            continue

        if in_comment:  # skip the rest of a multi-line author comment
            if "-->" in line:
                in_comment = False
            continue

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
                (notes if in_notes() else body).append(line)
            continue

        # Generic author comments (the slide/notes/@from forms are handled above):
        # drop them from the transcript, single- or multi-line.
        if "<!--" in line:
            head, rest = line.split("<!--", 1)
            if "-->" in rest:
                line = re.sub(r"<!--.*?-->", "", line)
            else:
                in_comment = True
                line = head
            if not line.strip():
                continue

        (notes if in_notes() else body).append(_clean(line))

    return body, notes, label


def _leads_with_heading(body: list[str]) -> bool:
    for line in body:
        if line.strip():
            return bool(_HEADING.match(line))
    return False


def build_outline(deck: AssembledDeck, config) -> str:
    """Render the assembled deck as a linear, heading-structured Markdown outline."""
    blocks: list[str] = [f"# {(config.title or '').strip() or 'Deck'}"]
    if (config.author or "").strip():
        blocks.append(f"_{config.author.strip()}_")

    number = 0
    for group in deck.slides():
        if is_blank_group(group):
            continue
        number += 1
        body, notes, label = _slide_parts(group)

        if not _leads_with_heading(body):
            blocks.append(f"## {(label or f'Slide {number}').strip()}")
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

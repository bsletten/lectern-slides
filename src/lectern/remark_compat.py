"""Remark input-compat: normalize legacy Remark syntax to neutral Lectern forms.

Existing decks authored for `remark.js <https://remarkjs.com>`_ use a handful of
Remark-specific constructs. When ``remark_compat`` is enabled, the assemble stage
runs each slide through :func:`normalize_remark_slide` so those decks render
through the modern (reveal) pipeline unchanged. New content should use the
neutral forms directly; this is a one-way migration aid, not a second syntax.

Conversions (per slide):

* **property lines** at the slide top — ``class: a, b`` → ``.a .b``,
  ``name: x`` → ``#x``, ``background-image: url(p)`` → a background data-attr —
  become a ``<!-- slide: … -->`` directive (``layout``/``template``/``count``
  degrade with a warning);
* ``.cls[content]`` → ``[content]{.cls}`` (inline) or ``::: {.cls}`` (block);
* ``--`` incremental separators → each following chunk wrapped in
  ``::: {.fragment}`` so the build survives the flatten;
* ``???`` speaker notes → ``<!-- notes -->`` … ``<!-- /notes -->``.
"""

from __future__ import annotations

import re

# Recognized Remark slide properties (only these start/extend a property block).
_KNOWN_PROPERTIES = {
    "class",
    "name",
    "background-image",
    "layout",
    "template",
    "count",
    "exclude",
}
_PROPERTY_LINE = re.compile(r"^([A-Za-z][\w-]*):\s*(.*)$")
_CLASS_OPEN = re.compile(r"\.([\w-]+)\[")
_URL = re.compile(r"url\(\s*['\"]?(.*?)['\"]?\s*\)")
# A class span may start at a line start or after whitespace/an opening delimiter.
_OPEN_CONTEXT = " \t\r\n([{>"


def normalize_remark_slide(text: str) -> tuple[str, list[str]]:
    """Return ``(neutral_text, warnings)`` for one Remark-syntax slide."""
    warnings: list[str] = []
    lines = text.split("\n")

    directive, body_lines = _extract_properties(lines, warnings)
    content, notes = _split_notes("\n".join(body_lines))
    content = _convert_increments(content)
    content = _convert_class_spans(content)

    parts: list[str] = []
    if directive:
        parts.append(directive)
        parts.append("")
    parts.append(content.strip("\n"))
    if notes is not None:
        parts.append("")
        parts.append("<!-- notes -->")
        parts.append(notes.strip("\n"))
        parts.append("<!-- /notes -->")

    return "\n".join(parts).strip("\n") + "\n", warnings


def _extract_properties(lines: list[str], warnings: list[str]) -> tuple[str, list[str]]:
    """Consume leading Remark property lines into a ``<!-- slide: … -->``."""
    classes: list[str] = []
    ident: str | None = None
    attrs: list[str] = []

    i = 0
    while i < len(lines):
        m = _PROPERTY_LINE.match(lines[i])
        if not m or m.group(1).lower() not in _KNOWN_PROPERTIES:
            break
        key, value = m.group(1).lower(), m.group(2).strip()
        if key == "class":
            classes.extend(t for t in re.split(r"[,\s]+", value) if t)
        elif key == "name":
            ident = value
        elif key == "background-image":
            url = _URL.search(value)
            attrs.append(f'data-background-image="{url.group(1) if url else value}"')
        else:  # layout / template / count / exclude
            warnings.append(f"unsupported Remark property '{key}' dropped")
        i += 1

    if not (classes or ident or attrs):
        return "", lines

    tokens = [f".{c}" for c in classes]
    if ident:
        tokens.append(f"#{ident}")
    tokens.extend(attrs)
    return f"<!-- slide: {' '.join(tokens)} -->", lines[i:]


def _split_notes(text: str) -> tuple[str, str | None]:
    """Split a slide on a bare ``???`` line into (content, notes)."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == "???":
            return "\n".join(lines[:i]), "\n".join(lines[i + 1 :])
    return text, None


def _convert_increments(text: str) -> str:
    """Flatten ``--`` incremental separators into ``::: {.fragment}`` blocks."""
    lines = text.split("\n")
    if not any(line.strip() == "--" for line in lines):
        return text

    chunks: list[list[str]] = [[]]
    for line in lines:
        if line.strip() == "--":
            chunks.append([])
        else:
            chunks[-1].append(line)

    out = ["\n".join(chunks[0]).strip("\n")]
    for chunk in chunks[1:]:
        body = "\n".join(chunk).strip("\n")
        out.append(f"\n::: {{.fragment}}\n\n{body}\n\n:::")
    return "\n".join(out)


def _match_bracket(text: str, start: int) -> tuple[str | None, int]:
    """Given ``start`` just past a ``[``, return (inner, index-after-]) balanced."""
    depth = 1
    i = start
    while i < len(text):
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
        i += 1
    return None, start


def _convert_class_spans(text: str) -> str:
    """Convert ``.cls[content]`` to ``[content]{.cls}`` / ``::: {.cls}`` blocks."""
    out: list[str] = []
    i = 0
    while i < len(text):
        m = _CLASS_OPEN.match(text, i)
        starts_ok = i == 0 or text[i - 1] in _OPEN_CONTEXT
        if m and starts_ok:
            inner, end = _match_bracket(text, m.end())
            if inner is None:  # unbalanced — leave the text as-is
                out.append(text[i])
                i += 1
                continue
            cls = m.group(1)
            inner = _convert_class_spans(inner)
            if "\n" in inner:
                out.append(f"\n::: {{.{cls}}}\n\n{inner.strip()}\n\n:::\n")
            else:
                out.append(f"[{inner}]{{.{cls}}}")
            i = end
        else:
            out.append(text[i])
            i += 1
    return "".join(out)

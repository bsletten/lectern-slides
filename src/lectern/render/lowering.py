"""Shared neutral-directive lowering for the native HTML adapters.

Both the reveal and remark adapters turn one assembled slide (a list of
:class:`OutLine`) into a framework-neutral intermediate, :class:`LoweredSlide`:
the slide's classes/id/data-attributes, its body (with ``::: {.cls}`` blocks and
``[text]{.cls}`` spans lowered to raw HTML and asset references rewritten), and
its speaker notes. Each adapter then formats that intermediate its own way
(reveal sections + ``Note:`` vs. remark property lines + ``???``).

The scan is fence-aware (code fences pass through untouched) and tracks the
current source file via the assembled ``@from`` provenance comments, so relative
asset references resolve against the file that authored them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..slides import closes_fence, fence_info, fence_marker

if TYPE_CHECKING:
    from ..assets import AssetResolver
    from ..sourcemap import OutLine

_PROVENANCE = re.compile(r"^<!-- @from (.+?) slide=\d+ -->$")
_SLIDE_DIRECTIVE = re.compile(r"^\s*<!--\s*slide:\s*(.+?)\s*-->\s*$")
# ``<!-- notes -->`` opens handout notes; ``<!-- notes:presenter -->`` opens
# speaker-view-only notes that are kept out of the PDF handout.
_NOTES_OPEN = re.compile(r"^\s*<!--\s*notes(?::([\w-]+))?\s*-->\s*$")
_NOTES_CLOSE = re.compile(r"^\s*<!--\s*/notes\s*-->\s*$")
_FENCE_DIV = re.compile(r"^(:::+)\s*(.*?)\s*$")
_INLINE_SPAN = re.compile(r"\[([^\]]+)\]\{([^}]*)\}")
# Only *top-level* list items become incremental fragments. A nested/indented
# item is a detail of its parent and rides in with it — making it its own build
# step puts it before its (still-hidden) parent in reveal's order, so the first
# presses reveal nothing visible. Matching column-0 markers keeps each numbered
# item and its sub-bullets a single step.
_LIST_ITEM = re.compile(r"^([-*+]|\d+[.)])\s+\S")
_TOKEN = re.compile(
    r"\.([\w-]+)"  # .class
    r"|#([\w-]+)"  # #id
    r"|([\w:-]+)=(?:\"([^\"]*)\"|'([^']*)'|(\S+))"  # key=value
)

# Directive/attribute values that name assets and should be resolved.
ASSET_ATTRS = {
    "data-background-image",
    "data-background-video",
    "poster",
    "src",
    "href",
}


def parse_tokens(spec: str) -> tuple[list[str], str | None, dict[str, str]]:
    """Parse ``.cls #id key=value`` tokens into (classes, id, attrs)."""
    classes: list[str] = []
    ident: str | None = None
    attrs: dict[str, str] = {}
    for m in _TOKEN.finditer(spec):
        if m.group(1):
            classes.append(m.group(1))
        elif m.group(2):
            ident = m.group(2)
        elif m.group(3):
            value = next((g for g in m.group(4, 5, 6) if g is not None), "")
            attrs[m.group(3)] = value
    return classes, ident, attrs


def parse_div(content: str) -> tuple[list[str], str | None, dict[str, str]]:
    """Parse a fenced-div header: ``{.a .b #id}`` or bare ``incremental``."""
    c = content.strip()
    if c.startswith("{") and c.endswith("}"):
        return parse_tokens(c[1:-1])
    return [w.lstrip(".") for w in c.split()], None, {}


def attr_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;")


def build_attrs(classes: list[str], ident: str | None, attrs: dict[str, str]) -> str:
    parts = [f'class="{" ".join(classes)}"'] if classes else []
    if ident:
        parts.append(f'id="{ident}"')
    for key, value in attrs.items():
        parts.append(f'{key}="{attr_escape(value)}"')
    return " ".join(parts)


def _span_repl(m: re.Match) -> str:
    classes, _ident, _attrs = parse_tokens(m.group(2))
    return f'<span class="{" ".join(classes)}">{m.group(1)}</span>'


@dataclass
class LoweredSlide:
    """A framework-neutral, lowered slide (directives resolved, HTML inlined)."""

    classes: list[str] = field(default_factory=list)
    ident: str | None = None
    attrs: dict[str, str] = field(default_factory=dict)
    body: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Speaker-view-only notes: shown alongside ``notes`` in every presenter view,
    # but excluded from the printed PDF handout.
    presenter_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    has_mermaid: bool = False

    @property
    def speaker_notes(self) -> list[str]:
        """All notes for a presenter view: handout notes plus presenter-only."""
        return self.notes + self.presenter_notes


class _Scanner:
    def __init__(self, resolver: AssetResolver, root: Path, incremental: str):
        self.resolver = resolver
        self.root = root
        self.incremental = incremental  # "fragment" | "degrade"
        self.out = LoweredSlide()
        self.current_dir = root
        self.label = "slide"
        self._label_set = False
        self._fence = None
        self._mermaid = None  # open ```mermaid fence, lowered to <pre class="mermaid">
        # "div" | "incremental" | "notes" | "notes:presenter"
        self._div_stack: list[str] = []
        self._directive_seen = False
        # The notes list the current comment/div block feeds, or None when not in
        # one — `out.notes` for handout notes, `out.presenter_notes` for speaker.
        self._notes_bucket: list[str] | None = None
        self._warned_incremental = False
        # Monotonic per-slide index for incremental list items, so reveal builds
        # them in source order regardless of which element `.element` lands on.
        self._frag_index = 0

    @property
    def _in_notes_div(self) -> bool:
        return bool(self._div_stack) and self._div_stack[-1].startswith("notes")

    def feed(self, line: str) -> None:
        prov = _PROVENANCE.match(line)
        if prov:
            display = prov.group(1)
            self.current_dir = (self.root / display).parent
            if not self._label_set:
                self.label = display
                self._label_set = True
            return

        if self._fence is not None:
            self.out.body.append(line)
            if closes_fence(line, self._fence):
                self._fence = None
            return

        # A ```mermaid block is lowered to a raw <pre class="mermaid"> (a
        # CommonMark type-1 HTML block): the Markdown renderers pass its body
        # through verbatim — so Mermaid's `-->` arrows survive and the highlight
        # plugin skips it — and the client-side Mermaid script renders it.
        if self._mermaid is not None:
            if closes_fence(line, self._mermaid):
                self.out.body.append("</pre>")
                self._mermaid = None
            else:
                self.out.body.append(line)
            return

        if self._notes_bucket is not None:
            if _NOTES_CLOSE.match(line):
                self._notes_bucket = None
            else:
                self._notes_bucket.append(line)
            return

        div = _FENCE_DIV.match(line)
        if div is not None and div.group(2) == "":
            if self._div_stack and self._div_stack.pop() == "div":
                self.out.body.extend(["", "</div>"])
            return

        if self._in_notes_div:
            presenter = self._div_stack[-1] == "notes:presenter"
            (self.out.presenter_notes if presenter else self.out.notes).append(line)
            return

        notes_open = _NOTES_OPEN.match(line)
        if notes_open is not None:
            category = notes_open.group(1)
            if category is not None and category != "presenter":
                # A mistyped category would silently fall through to handout
                # notes and leak into the PDF — flag it instead.
                self.out.warnings.append(
                    f"{self.label}: unknown notes category '{category}'; "
                    "only 'presenter' is recognized — treating as ordinary notes"
                )
            self._notes_bucket = (
                self.out.presenter_notes if category == "presenter" else self.out.notes
            )
            return

        if not self._directive_seen:
            directive = _SLIDE_DIRECTIVE.match(line)
            if directive is not None:
                self._apply_directive(directive.group(1))
                self._directive_seen = True
                return

        if div is not None:
            self._open_div(div.group(2))
            return

        marker = fence_marker(line)
        if marker is not None:
            if fence_info(line).split(" ")[0].lower() == "mermaid":
                self._mermaid = marker
                self.out.has_mermaid = True
                self.out.body.append('<pre class="mermaid">')
                return
            self._fence = marker
            self.out.body.append(line)
            return

        self.out.body.append(self._lower_content(line))

    def _apply_directive(self, spec: str) -> None:
        classes, ident, attrs = parse_tokens(spec)
        self.out.classes.extend(classes)
        if ident:
            self.out.ident = ident
        for key, value in attrs.items():
            # `label` is a friendly alias for the slide's accessible name.
            if key == "label":
                key = "aria-label"
            elif key.lower() in ASSET_ATTRS:
                value = self.resolver.resolve(value, self.current_dir, self.label)
            self.out.attrs[key] = value

    def _open_div(self, content: str) -> None:
        classes, ident, attrs = parse_div(content)
        if classes == ["incremental"]:
            self._div_stack.append("incremental")
            if self.incremental == "degrade" and not self._warned_incremental:
                self.out.warnings.append(
                    f"{self.label}: incremental builds are not supported by this "
                    "renderer; the list will render all at once"
                )
                self._warned_incremental = True
        elif classes == ["notes"]:
            self._div_stack.append("notes")
        elif set(classes) == {"notes", "presenter"}:
            self._div_stack.append("notes:presenter")
        else:
            self._div_stack.append("div")
            self.out.body.extend([f"<div {build_attrs(classes, ident, attrs)}>", ""])

    def _lower_content(self, line: str) -> str:
        out = line
        if (
            self.incremental == "fragment"
            and "incremental" in self._div_stack
            and _LIST_ITEM.match(out)
        ):
            # `data-li-frag` marks an incremental list item; its value is the
            # item's source-order index within the slide. reveal's `.element`
            # comment attaches the class to the *preceding inline element* (a
            # <strong>/<em>) when the item is formatted, not the <li> — so only
            # the formatted text would build, not the item or its number. Worse,
            # a plain item lands the class on the <li> directly and becomes a
            # fragment at load (index 0) while formatted items are promoted later
            # and appended after it — so builds fire out of order. A client script
            # (see the reveal template) promotes the fragment to the <li> and
            # copies this index into `data-fragment-index` to pin source order.
            out = (
                out.rstrip()
                + f' <!-- .element: class="fragment" data-li-frag="{self._frag_index}" -->'
            )
            self._frag_index += 1
        out = _INLINE_SPAN.sub(_span_repl, out)
        return self.resolver.rewrite(out, self.current_dir, self.label)

    def finish(self) -> LoweredSlide:
        if self._mermaid is not None:
            self.out.body.append("</pre>")
            self._mermaid = None
        while self._div_stack:
            if self._div_stack.pop() == "div":
                self.out.body.extend(["", "</div>"])
        return self.out


def scan_slide(
    group: list[OutLine],
    resolver: AssetResolver,
    root: Path,
    *,
    incremental: str = "fragment",
) -> LoweredSlide:
    """Lower one assembled slide into a :class:`LoweredSlide`."""
    scanner = _Scanner(resolver, root, incremental)
    for outline in group:
        scanner.feed(outline.text)
    return scanner.finish()


def is_blank_group(outlines: list[OutLine]) -> bool:
    """Whether a slide group has no real content (only blanks/provenance)."""
    return all(not o.text.strip() or o.text.startswith("<!-- @from ") for o in outlines)

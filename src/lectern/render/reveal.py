"""The native ``reveal`` adapter (default; no external binary).

Each assembled slide becomes a ``<section class="slide …" data-markdown>`` whose
body is rendered client-side by reveal's Markdown plugin. We do the *neutral →
reveal* lowering as text transforms before embedding:

* ``<!-- slide: .center .middle #id data-background-image="x" -->`` → section
  classes / id / data-attributes (background image refs are asset-resolved);
* ``<!-- notes -->…<!-- /notes -->`` (and ``::: notes``) → reveal speaker notes;
* ``::: {.cls}`` … ``:::`` → ``<div class="cls">`` (so ``.place`` boxes work);
* ``::: incremental`` → each list child tagged ``.fragment``;
* ``[text]{.cls}`` → ``<span class="cls">text</span>``.

Lowering is fence-aware (code fences pass through untouched) and tracks the
current source file via the assembled ``@from`` provenance comments, so relative
asset references resolve against the file that actually authored them.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, select_autoescape

from ..assets import AssetResolver
from ..slides import closes_fence, fence_marker
from ..theming import build_theme
from .base import Caps, RenderResult, register

if TYPE_CHECKING:
    from ..config import Config
    from ..preprocess import AssembledDeck
    from ..sourcemap import OutLine

REVEAL_VERSION = "5.1.0"
REVEAL_CDN = f"https://cdn.jsdelivr.net/npm/reveal.js@{REVEAL_VERSION}"
KATEX_CDN = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css"

_PROVENANCE = re.compile(r"^<!-- @from (.+?) slide=\d+ -->$")
_SLIDE_DIRECTIVE = re.compile(r"^\s*<!--\s*slide:\s*(.+?)\s*-->\s*$")
_NOTES_OPEN = re.compile(r"^\s*<!--\s*notes\s*-->\s*$")
_NOTES_CLOSE = re.compile(r"^\s*<!--\s*/notes\s*-->\s*$")
_FENCE_DIV = re.compile(r"^(:::+)\s*(.*?)\s*$")
_INLINE_SPAN = re.compile(r"\[([^\]]+)\]\{([^}]*)\}")
_LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s+\S")
_TOKEN = re.compile(
    r"\.([\w-]+)"  # .class
    r"|#([\w-]+)"  # #id
    r"|([\w:-]+)=(?:\"([^\"]*)\"|'([^']*)'|(\S+))"  # key=value
)

# Directive/attribute values that name assets and should be resolved.
_ASSET_ATTRS = {
    "data-background-image",
    "data-background-video",
    "poster",
    "src",
    "href",
}


def _parse_tokens(spec: str) -> tuple[list[str], str | None, dict[str, str]]:
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


def _parse_div(content: str) -> tuple[list[str], str | None, dict[str, str]]:
    """Parse a fenced-div header: ``{.a .b #id}`` or bare ``incremental``."""
    c = content.strip()
    if c.startswith("{") and c.endswith("}"):
        return _parse_tokens(c[1:-1])
    return [w.lstrip(".") for w in c.split()], None, {}


def _attr_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;")


def _build_attrs(classes: list[str], ident: str | None, attrs: dict[str, str]) -> str:
    parts = [f'class="{" ".join(classes)}"'] if classes else []
    if ident:
        parts.append(f'id="{ident}"')
    for key, value in attrs.items():
        parts.append(f'{key}="{_attr_escape(value)}"')
    return " ".join(parts)


def _span_repl(m: re.Match) -> str:
    classes, _ident, _attrs = _parse_tokens(m.group(2))
    return f'<span class="{" ".join(classes)}">{m.group(1)}</span>'


class _SlideLowering:
    """Lower one assembled slide's OutLines into a reveal ``<section>``."""

    def __init__(self, resolver: AssetResolver, root: Path):
        self.resolver = resolver
        self.root = root
        self.classes = ["slide"]
        self.ident: str | None = None
        self.section_attrs: dict[str, str] = {}
        self.body: list[str] = []
        self.notes: list[str] = []
        self.current_dir = root
        self.label = "slide"
        self._label_set = False
        self._fence = None
        self._div_stack: list[str] = []  # "div" | "incremental" | "notes"
        self._directive_seen = False
        self._notes_comment = False

    @property
    def _in_notes_div(self) -> bool:
        return bool(self._div_stack) and self._div_stack[-1] == "notes"

    def feed(self, line: str) -> None:
        prov = _PROVENANCE.match(line)
        if prov:
            display = prov.group(1)
            self.current_dir = (self.root / display).parent
            if not self._label_set:
                self.label = display
                self._label_set = True
            return

        # Inside a code fence: pass through verbatim, watch for the close.
        if self._fence is not None:
            self.body.append(line)
            if closes_fence(line, self._fence):
                self._fence = None
            return

        if self._notes_comment:
            if _NOTES_CLOSE.match(line):
                self._notes_comment = False
            else:
                self.notes.append(line)
            return

        # A bare ``:::`` closes the innermost block (incl. a ``::: notes`` block).
        div = _FENCE_DIV.match(line)
        if div is not None and div.group(2) == "":
            if self._div_stack:
                kind = self._div_stack.pop()
                if kind == "div":
                    self.body.extend(["", "</div>"])
            return

        if self._in_notes_div:
            self.notes.append(line)
            return

        if _NOTES_OPEN.match(line):
            self._notes_comment = True
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
            self._fence = marker
            self.body.append(line)
            return

        self.body.append(self._lower_content(line))

    def _apply_directive(self, spec: str) -> None:
        classes, ident, attrs = _parse_tokens(spec)
        self.classes.extend(classes)
        if ident:
            self.ident = ident
        for key, value in attrs.items():
            if key.lower() in _ASSET_ATTRS:
                value = self.resolver.resolve(value, self.current_dir, self.label)
            self.section_attrs[key] = value

    def _open_div(self, content: str) -> None:
        classes, ident, attrs = _parse_div(content)
        if classes == ["incremental"]:
            self._div_stack.append("incremental")
        elif classes == ["notes"]:
            self._div_stack.append("notes")
        else:
            self._div_stack.append("div")
            self.body.extend([f"<div {_build_attrs(classes, ident, attrs)}>", ""])

    def _lower_content(self, line: str) -> str:
        out = line
        if "incremental" in self._div_stack and _LIST_ITEM.match(out):
            out = out.rstrip() + ' <!-- .element: class="fragment" -->'
        out = _INLINE_SPAN.sub(_span_repl, out)
        return self.resolver.rewrite(out, self.current_dir, self.label)

    def finish(self) -> dict[str, str]:
        # Close any divs the author left open, so the section stays well-formed.
        while self._div_stack:
            if self._div_stack.pop() == "div":
                self.body.extend(["", "</div>"])
        markdown = "\n".join(self.body).strip("\n")
        if self.notes:
            notes = "\n".join(self.notes).strip("\n")
            markdown = f"{markdown}\n\nNote:\n{notes}"
        # ``</script>`` would close the data-markdown template early.
        markdown = markdown.replace("</script>", "<\\/script>")
        return {
            "attrs": _build_attrs(self.classes, self.ident, self.section_attrs),
            "markdown": markdown,
        }


def _is_blank(outlines: list[OutLine]) -> bool:
    return all(not o.text.strip() or o.text.startswith("<!-- @from ") for o in outlines)


class RevealRenderer:
    name = "reveal"

    def available(self) -> bool:  # native — always available
        return True

    def capabilities(self) -> Caps:
        return Caps(html=True, pdf=False, pptx=False, embeds=True)

    def render(
        self, deck: AssembledDeck, config: Config, out_dir: Path
    ) -> RenderResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        warnings = list(deck.warnings)
        resolver = AssetResolver(deck.root, config.asset_base, out_dir, warnings)
        theme = build_theme(config.theme, config.aspect, deck.root)

        slides = []
        for group in deck.slides():
            if _is_blank(group):
                continue
            lowering = _SlideLowering(resolver, deck.root)
            for outline in group:
                lowering.feed(outline.text)
            slides.append(lowering.finish())

        html_text = _render_template(deck, config, theme, slides)
        output = out_dir / "index.html"
        output.write_text(html_text, encoding="utf-8")

        return RenderResult(output=output, assets=resolver.copied, warnings=warnings)


def _render_template(deck, config, theme, slides) -> str:
    rc = config.reveal.model_dump()
    math = rc.get("math") or False
    highlight = bool(rc.get("highlight", True))

    init = {
        "width": theme.width,
        "height": theme.height,
        "margin": 0.04,
        "center": False,
        "hash": True,
        "controls": bool(rc.get("controls", True)),
        "progress": bool(rc.get("progress", True)),
        "transition": rc.get("transition", "none"),
        "slideNumber": rc.get("slide_number", False),
    }

    plugins = ["RevealMarkdown", "RevealNotes"]
    if highlight:
        plugins.append("RevealHighlight")
    if math:
        plugins.append("RevealMath.KaTeX" if math == "katex" else "RevealMath.MathJax3")

    env = Environment(
        loader=PackageLoader("lectern", "templates"),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("reveal.html.j2")
    return template.render(
        title=html.escape(config.title or theme.name),
        author=html.escape(config.author or ""),
        theme_css=theme.css,
        reveal_cdn=REVEAL_CDN,
        katex_cdn=KATEX_CDN,
        init_json=json.dumps(init),
        plugins=plugins,
        highlight=highlight,
        math=math,
        slides=slides,
    )


register(RevealRenderer())

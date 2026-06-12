"""The ``quarto`` adapter — a subprocess wrapper around `quarto render`.

Lowers the assembled deck to a Quarto `.qmd` and shells out to ``quarto`` to
produce a high-quality reveal.js deck (Quarto's strength: typography, embedding,
self-contained output). Quarto is *not* a dependency: :meth:`available` guards the
binary. PDF/PPTX are out of scope here — Quarto's PDF path is browser-print or
Beamer, neither a clean CLI target — so this adapter advertises HTML only and the
build degrades to Marp (or reveal print) for those formats.

Lowering, via the shared :mod:`lectern.render.lowering` scanner:

* slides are separated by ``---`` horizontal rules with ``slide-level: 0`` (so
  Quarto makes one reveal section per Lectern slide, regardless of headings);
* each slide's content is wrapped in ``<div class="slide …">`` so the Lectern
  theme's class-based rules (``.inverse``, ``.center``, anchors) apply inside
  Quarto's reveal ``<section>`` — the theme CSS is passed through Quarto's own
  ``css:`` mechanism;
* ``::: {.cls}`` / ``[text]{.cls}`` → raw HTML; ``data-background-image`` → an
  inline ``background-image`` style on the wrapper; ``<!-- notes -->`` →
  ``<aside class="notes">`` (reveal's speaker-notes element).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from ..assets import AssetResolver
from ..slides import closes_fence, fence_marker
from ..theming import build_theme
from ._external import run_tool, tool_available
from .base import Caps, RenderResult, register
from .lowering import build_attrs, is_blank_group, scan_slide

if TYPE_CHECKING:
    from ..config import Config
    from ..preprocess import AssembledDeck

BINARY = "quarto"
_THEME_CSS = "lectern-theme.css"
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _html_headings(body: list[str]) -> list[str]:
    """Convert Markdown ATX headings to raw HTML ``<hN>`` (fence-aware).

    Quarto/reveal starts a new slide at *every* Markdown heading, which would
    shatter a Lectern slide that contains one. Emitting the heading as raw HTML
    keeps it as in-slide content (still themed by ``.slide hN``) so the ``---``
    horizontal rule stays the sole slide separator. Inline Markdown inside a
    heading is not reprocessed — slide headings are virtually always plain text.
    """
    out: list[str] = []
    fence = None
    for line in body:
        if fence is not None:
            out.append(line)
            if closes_fence(line, fence):
                fence = None
            continue
        marker = fence_marker(line)
        if marker is not None:
            fence = marker
            out.append(line)
            continue
        m = _HEADING.match(line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{m.group(2)}</h{level}>")
        else:
            out.append(line)
    return out


def _format_slide(lowered, warnings: list[str]) -> str:
    """Format one lowered slide as a wrapped Quarto/reveal HTML block + notes."""
    classes = ["slide", *lowered.classes]
    attrs: dict[str, str] = {}
    bg = lowered.attrs.get("data-background-image")
    if bg:
        attrs["style"] = f"background-image:url({bg});background-size:cover"
    if "aria-label" in lowered.attrs:  # accessible name -> the wrapper div
        attrs["aria-label"] = lowered.attrs["aria-label"]
    for key in lowered.attrs:
        if key not in ("data-background-image", "aria-label"):
            warnings.append(
                f"quarto: slide attribute '{key}' is not supported and was dropped"
            )

    body = "\n".join(_html_headings(lowered.body)).strip("\n")
    open_tag = f"<div {build_attrs(classes, lowered.ident, attrs)}>"
    parts = [open_tag, "", body, "", "</div>"]
    if lowered.notes:
        notes = "\n".join(lowered.notes).strip("\n")
        parts.extend(["", '<aside class="notes">', "", notes, "", "</aside>"])
    return "\n".join(parts).strip("\n")


def _yaml_block(width: int, height: int, math, passthrough: dict) -> list[str]:
    """The ``format: revealjs`` front-matter lines for the deck."""
    lines = [
        "format:",
        "  revealjs:",
        "    slide-level: 0",
        f"    width: {width}",
        f"    height: {height}",
        f"    css: {_THEME_CSS}",
        "    embed-resources: true",
    ]
    if math:
        method = "mathjax" if math == "mathjax" else "katex"
        lines.append(f"    html-math-method: {method}")
    for key, value in passthrough.items():
        lines.append(f"    {str(key).replace('_', '-')}: {_yaml_scalar(value)}")
    return lines


def _yaml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'


def build_source(config: Config, theme, slides: list[str]) -> str:
    """Assemble the full `.qmd` document (front-matter + horizontal-rule slides)."""
    yaml = _yaml_block(theme.width, theme.height, config.reveal.math, config.quarto)
    front = ["---", *yaml, "---"]
    body = "\n\n---\n\n".join(slides)
    return "\n".join(front) + "\n\n" + body + "\n"


class QuartoRenderer:
    name = "quarto"

    def available(self) -> bool:
        return tool_available(BINARY)

    def capabilities(self) -> Caps:
        return Caps(html=True, pdf=False, pptx=False, embeds=True)

    def render(
        self, deck: AssembledDeck, config: Config, out_dir: Path, fmt: str = "html"
    ) -> RenderResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        warnings = list(deck.warnings)
        resolver = AssetResolver(deck.root, config.asset_base, out_dir, warnings)
        theme = build_theme(config.theme, config.aspect, deck.root, config.theme_paths)

        slides = []
        for group in deck.slides():
            if is_blank_group(group):
                continue
            lowered = scan_slide(group, resolver, deck.root, incremental="degrade")
            warnings.extend(lowered.warnings)
            slides.append(_format_slide(lowered, warnings))

        (out_dir / _THEME_CSS).write_text(theme.css, encoding="utf-8")
        src_path = out_dir / "deck.qmd"
        src_path.write_text(build_source(config, theme, slides), encoding="utf-8")

        output = out_dir / "index.html"
        cmd = [
            BINARY,
            "render",
            src_path.name,
            "--to",
            "revealjs",
            "--output",
            output.name,
        ]
        run_tool(cmd, cwd=out_dir, tool="quarto")

        return RenderResult(output=output, assets=resolver.copied, warnings=warnings)


register(QuartoRenderer())

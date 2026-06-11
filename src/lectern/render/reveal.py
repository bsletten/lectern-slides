"""The native ``reveal`` adapter (default; no external binary).

Each assembled slide becomes a ``<section class="slide …" data-markdown>`` whose
body is rendered client-side by reveal's Markdown plugin. The neutral → reveal
lowering (slide directive → section classes/id/data-attrs, ``::: {.cls}`` →
``<div>``, ``::: incremental`` → ``.fragment``, ``[text]{.cls}`` → ``<span>``,
notes → reveal speaker notes, assets resolved) is shared with the remark adapter
in :mod:`lectern.render.lowering`; here we just format each lowered slide as a
reveal ``<section>``.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, select_autoescape

from ..assets import AssetResolver
from ..theming import build_theme
from .base import Caps, RenderResult, register
from .lowering import build_attrs, is_blank_group, scan_slide

if TYPE_CHECKING:
    from ..config import Config
    from ..preprocess import AssembledDeck

REVEAL_VERSION = "5.1.0"
REVEAL_CDN = f"https://cdn.jsdelivr.net/npm/reveal.js@{REVEAL_VERSION}"
KATEX_CDN = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css"


def _format_slide(lowered) -> dict[str, str]:
    """Format a lowered slide as a reveal ``<section>`` (attrs + body markdown)."""
    classes = ["slide", *lowered.classes]
    markdown = "\n".join(lowered.body).strip("\n")
    if lowered.notes:
        notes = "\n".join(lowered.notes).strip("\n")
        markdown = f"{markdown}\n\nNote:\n{notes}"
    # ``</script>`` would close the data-markdown template early.
    markdown = markdown.replace("</script>", "<\\/script>")
    return {
        "attrs": build_attrs(classes, lowered.ident, lowered.attrs),
        "markdown": markdown,
    }


class RevealRenderer:
    name = "reveal"

    def available(self) -> bool:  # native — always available
        return True

    def capabilities(self) -> Caps:
        return Caps(html=True, pdf=False, pptx=False, embeds=True)

    def render(
        self, deck: AssembledDeck, config: Config, out_dir: Path, fmt: str = "html"
    ) -> RenderResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        warnings = list(deck.warnings)
        resolver = AssetResolver(deck.root, config.asset_base, out_dir, warnings)
        theme = build_theme(config.theme, config.aspect, deck.root)

        slides = []
        for group in deck.slides():
            if is_blank_group(group):
                continue
            lowered = scan_slide(group, resolver, deck.root, incremental="fragment")
            warnings.extend(lowered.warnings)
            slides.append(_format_slide(lowered))

        html_text = _render_template(config, theme, slides)
        output = out_dir / "index.html"
        output.write_text(html_text, encoding="utf-8")

        return RenderResult(output=output, assets=resolver.copied, warnings=warnings)


def _render_template(config, theme, slides) -> str:
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

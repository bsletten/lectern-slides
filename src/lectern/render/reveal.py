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
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"


def _format_slide(lowered) -> dict[str, str]:
    """Format a lowered slide as a reveal ``<section>`` (attrs + body markdown)."""
    classes = ["slide", *lowered.classes]
    markdown = "\n".join(lowered.body).strip("\n")
    if lowered.speaker_notes:
        notes = "\n".join(lowered.speaker_notes).strip("\n")
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
        # PDF is produced by the headless-Chromium master pipeline (the [pdf] extra).
        return Caps(html=True, pdf=True, pptx=False, embeds=True)

    def render(
        self, deck: AssembledDeck, config: Config, out_dir: Path, fmt: str = "html"
    ) -> RenderResult:
        if fmt == "pdf":
            from ..pdf.pipeline import build_pdf

            return build_pdf(deck, config, out_dir)

        out_dir.mkdir(parents=True, exist_ok=True)
        warnings = list(deck.warnings)
        html_text, resolver, _theme = build_html(deck, config, out_dir, warnings)
        output = out_dir / "index.html"
        output.write_text(html_text, encoding="utf-8")
        # Garbage-collect orphaned content-hashed assets from prior builds, so a
        # plain `build` leaves the same assets/ a clean rebuild would.
        pruned = resolver.prune_stale()

        return RenderResult(
            output=output,
            assets=resolver.copied,
            warnings=warnings,
            pruned=len(pruned),
        )


def build_html(
    deck: AssembledDeck,
    config: Config,
    out_dir: Path,
    warnings: list[str],
    *,
    init_extra: dict | None = None,
    extra_head: str = "",
):
    """Assemble the reveal HTML; copy assets into ``out_dir``.

    Returns ``(html_text, resolver, theme)``. ``init_extra`` merges into the reveal
    ``initialize`` config and ``extra_head`` is injected at the end of ``<head>`` —
    the seams the PDF master uses to flatten fragments and inject print CSS.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    resolver = AssetResolver(deck.root, config.asset_base, out_dir, warnings)
    theme = build_theme(config.theme, config.aspect, deck.root, deck.theme_dirs)

    slides = []
    mermaid_seen = False
    for group in deck.slides():
        if is_blank_group(group):
            continue
        lowered = scan_slide(group, resolver, deck.root, incremental="fragment")
        warnings.extend(lowered.warnings)
        mermaid_seen = mermaid_seen or lowered.has_mermaid
        slides.append(_format_slide(lowered))

    # `[reveal].mermaid`: None = auto (load iff a diagram is present), else force.
    forced = config.reveal.model_dump().get("mermaid")
    mermaid = mermaid_seen if forced is None else bool(forced)

    from .. import fontawesome
    from ..metadata import render_script

    fa_css = fontawesome.resolve(config.font_awesome, deck.root, out_dir, warnings)
    json_ld = render_script(config, getattr(deck, "tags", None))

    html_text = _render_template(
        config,
        theme,
        slides,
        mermaid=mermaid,
        font_awesome_css=fa_css,
        init_extra=init_extra,
        extra_head=extra_head,
        json_ld=json_ld,
    )
    return html_text, resolver, theme


def _render_template(
    config,
    theme,
    slides,
    *,
    mermaid=False,
    font_awesome_css=None,
    init_extra=None,
    extra_head="",
    json_ld="",
) -> str:
    rc = config.reveal.model_dump()
    math = rc.get("math") or False
    highlight = bool(rc.get("highlight", True))

    init = {
        "width": theme.width,
        "height": theme.height,
        "margin": 0.04,
        "center": False,
        # Use flex (not reveal's default block) as the display value for visible
        # slides, so the themed `.slide` flex layout — and its `.middle`/`.bottom`
        # anchor-grid centering — is what reveal applies inline while a slide is
        # shown. This holds through transitions: a leaving slide stays flex-
        # centered as it fades instead of snapping to block (top-aligned), which
        # caused a visible text flash. Far slides still get `display:none`, so
        # viewDistance/lazy embeds are unaffected.
        "display": "flex",
        "hash": True,
        "controls": bool(rc.get("controls", True)),
        "progress": bool(rc.get("progress", True)),
        "transition": rc.get("transition", "none"),
        # Switch slide backgrounds instantly. Slide backgrounds here are opaque
        # theme fills on the section; reveal's default `fade` crossfades its
        # separate background layer, and mid-crossfade both copies are partly
        # transparent — so the (light) viewport bleeds through as a flash, most
        # visible going to/from/between dark `.inverse` slides. Content still
        # honors `[reveal].transition`; only the background stops crossfading.
        "backgroundTransition": "none",
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
        lang=html.escape(config.lang or "en"),
        theme_css=theme.css,
        reveal_cdn=REVEAL_CDN,
        katex_cdn=KATEX_CDN,
        mermaid_cdn=MERMAID_CDN,
        mermaid=mermaid,
        font_awesome_css=font_awesome_css,
        init_json=json.dumps(init),
        init_extra=json.dumps(init_extra) if init_extra else "",
        extra_head=extra_head,
        json_ld=json_ld,
        plugins=plugins,
        highlight=highlight,
        math=math,
        slides=slides,
    )


register(RevealRenderer())

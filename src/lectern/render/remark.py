"""The native ``remark`` adapter — the legacy/parity path.

Renders the assembled deck with `remark.js <https://remarkjs.com>`_. remark
understands its own syntax natively (``class:`` property lines, ``.cls[…]``,
``--`` increments, ``???`` notes), so a legacy deck rendered here looks as it
always did. Neutral Lectern directives are lowered to remark equivalents via the
shared :mod:`lectern.render.lowering` scanner: the slide directive becomes
property lines, ``::: {.cls}`` / ``[text]{.cls}`` become raw HTML (the theme's
classes are framework-independent), and ``<!-- notes -->`` becomes ``???``.

A single injected ``layout: true`` template slide gives every slide the ``slide``
class, so the ``.slide``-targeted theme applies while each slide's own property
lines are left untouched (the key to rendering existing decks unchanged).
``::: incremental`` and math typesetting degrade with a warning.
"""

from __future__ import annotations

import html
import json
from math import gcd
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, select_autoescape

from ..assets import AssetResolver
from ..theming import build_theme
from .base import Caps, RenderResult, register
from .lowering import is_blank_group, scan_slide

if TYPE_CHECKING:
    from ..config import Config
    from ..preprocess import AssembledDeck

# remark.js distributes a single bundle from its own site.
REMARK_CDN = "https://remarkjs.com/downloads/remark-latest.min.js"

# Every content slide inherits `slide` from this template, so the theme applies.
_LAYOUT_SLIDE = "layout: true\nclass: slide\n"


def _format_slide(lowered, warnings: list[str]) -> str:
    """Format a lowered slide as remark Markdown (property lines + body + notes)."""
    header: list[str] = []
    if lowered.classes:
        header.append(f"class: {', '.join(lowered.classes)}")
    if lowered.ident:
        header.append(f"name: {lowered.ident}")
    bg = lowered.attrs.get("data-background-image")
    if bg:
        header.append(f"background-image: url({bg})")
    for key in lowered.attrs:
        if key != "data-background-image":
            warnings.append(
                f"remark: slide attribute '{key}' is not supported and was dropped"
            )

    parts: list[str] = []
    if header:
        parts.append("\n".join(header))
        parts.append("")  # blank line ends the property block
    parts.append("\n".join(lowered.body).strip("\n"))
    if lowered.notes:
        parts.append("")
        parts.append("???")
        parts.append("\n".join(lowered.notes).strip("\n"))
    return "\n".join(parts).strip("\n")


class RemarkRenderer:
    name = "remark"

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

        if config.reveal.math:
            warnings.append("remark: math typesetting is not supported by this adapter")

        slide_mds = []
        for group in deck.slides():
            if is_blank_group(group):
                continue
            lowered = scan_slide(group, resolver, deck.root, incremental="degrade")
            warnings.extend(lowered.warnings)
            slide_mds.append(_format_slide(lowered, warnings))

        source = _LAYOUT_SLIDE + "\n---\n\n" + "\n\n---\n\n".join(slide_mds) + "\n"
        html_text = _render_template(config, theme, source)
        output = out_dir / "index.html"
        output.write_text(html_text, encoding="utf-8")

        return RenderResult(output=output, assets=resolver.copied, warnings=warnings)


def _reduced_ratio(width: int, height: int) -> str:
    g = gcd(width, height) or 1
    return f"{width // g}:{height // g}"


def _render_template(config, theme, source: str) -> str:
    # Escape ``</`` so a slide containing ``</script>`` can't close the inline
    # bootstrap script early; ``<\/`` is still a valid JSON/JS string.
    source_json = json.dumps(source).replace("</", "<\\/")

    env = Environment(
        loader=PackageLoader("lectern", "templates"),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("remark.html.j2")
    return template.render(
        title=html.escape(config.title or theme.name),
        author=html.escape(config.author or ""),
        theme_css=theme.css,
        remark_cdn=REMARK_CDN,
        ratio=_reduced_ratio(theme.width, theme.height),
        source_json=source_json,
    )


register(RemarkRenderer())

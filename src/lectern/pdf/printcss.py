"""The injected print stylesheet — render-time master tweaks, theme-agnostic.

Built from :class:`~lectern.pdf.options.PdfOptions` and the theme CSS, injected
*after* the theme so it wins, and relying only on the theme **token contract**
(``--bg``/``--fg``/``--inverse-*``…). That means ``backgrounds=off``,
``light_inverse``, and the ``tokens`` B&W engine work for any conforming theme
without the theme shipping its own print block.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .colors import gray_token_overrides

if TYPE_CHECKING:
    from .options import PdfOptions

# Slides flagged dark; flipping them to the light tokens is the whole job for both
# `light_inverse` and `backgrounds=off` (ink economy / clean white paper).
_INVERSE_TO_LIGHT = """\
.reveal .slides section.slide.inverse {
  background: var(--bg) !important;
  color: var(--fg) !important;
}
.reveal .slides section.slide.inverse h1,
.reveal .slides section.slide.inverse h2,
.reveal .slides section.slide.inverse a { color: var(--fg) !important; }"""

# Drop every background paint so nothing but content reaches the page.
_NO_BACKGROUNDS = """\
.reveal, .reveal .slides, .reveal .backgrounds, .reveal .slide-background,
.reveal .slide-background-content { background: #fff !important; }
.reveal .slide-background-content { background-image: none !important; }
section[data-background-image], section[data-background-video],
section[data-background-color], section[data-background] {
  background: #fff !important;
}"""


def build(options: PdfOptions, theme_css: str) -> str:
    """The print stylesheet for this export (may be empty for a plain color 1-up)."""
    blocks: list[str] = []

    if not options.backgrounds:
        blocks.append(_NO_BACKGROUNDS)
    if options.light_inverse or not options.backgrounds:
        blocks.append(_INVERSE_TO_LIGHT)

    if options.bw and options.bw_engine == "tokens":
        grays = gray_token_overrides(theme_css)
        if grays:
            decls = "\n".join(f"  {k}: {v};" for k, v in grays.items())
            blocks.append(f":root {{\n{decls}\n}}")

    if not blocks:
        return ""
    return "/* lectern: print master tweaks */\n" + "\n\n".join(blocks) + "\n"

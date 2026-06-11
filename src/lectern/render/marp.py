"""The ``marp`` adapter — a subprocess wrapper around `marp-cli`.

Lowers the assembled deck to Marp Markdown and shells out to ``marp`` to produce
HTML, PDF, or PPTX. Marp is *not* a dependency: :meth:`available` guards the
binary, and the build degrades with a single warning (never a crash) for neutral
features Marp can't honor — incremental builds, slide ``id``/``data-*`` attrs.

Lowering, via the shared :mod:`lectern.render.lowering` scanner:

* the slide directive's classes → a scoped ``<!-- _class: slide … -->`` (the
  ``slide`` class is what makes the Lectern theme apply, exactly as in reveal);
* ``data-background-image`` → ``<!-- _backgroundImage: "url(…)" -->``;
* ``::: {.cls}`` / ``[text]{.cls}`` → raw HTML (passed through with ``--html``);
* ``<!-- notes -->`` → a plain HTML comment, which Marp treats as presenter notes;
* the Lectern theme CSS is injected as a global ``<style>`` block (Marp's own
  theme mechanism), with the deck's slide geometry appended.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..assets import AssetResolver
from ..theming import build_theme
from ._external import run_tool, tool_available
from .base import Caps, RenderResult, register
from .lowering import is_blank_group, scan_slide

if TYPE_CHECKING:
    from ..config import Config
    from ..preprocess import AssembledDeck

BINARY = "marp"
# Requested format → (output filename, marp-cli flag forcing that conversion).
# HTML is marp-cli's default (the ``-o`` extension implies it), so no flag.
_FORMATS = {
    "html": ("index.html", None),
    "pdf": ("index.pdf", "--pdf"),
    "pptx": ("index.pptx", "--pptx"),
}


def _format_slide(lowered, warnings: list[str]) -> str:
    """Format one lowered slide as Marp Markdown (spot directives + body + notes)."""
    directives: list[str] = []
    classes = ["slide", *lowered.classes]
    directives.append(f"<!-- _class: {' '.join(classes)} -->")

    bg = lowered.attrs.get("data-background-image")
    if bg:
        directives.append(f'<!-- _backgroundImage: "url({bg})" -->')
    if lowered.ident:
        warnings.append(
            f"marp: slide id '{lowered.ident}' is not supported and was dropped"
        )
    for key in lowered.attrs:
        if key != "data-background-image":
            warnings.append(
                f"marp: slide attribute '{key}' is not supported and was dropped"
            )

    parts = ["\n".join(directives), ""]
    parts.append("\n".join(lowered.body).strip("\n"))
    if lowered.notes:
        notes = "\n".join(lowered.notes).strip("\n")
        # A presenter note is just a (non-directive) HTML comment; guard ``-->``.
        notes = notes.replace("-->", "--&gt;")
        parts.append("")
        parts.append(f"<!--\n{notes}\n-->")
    return "\n".join(parts).strip("\n")


def build_source(config: Config, theme, slides: list[str]) -> str:
    """Assemble the full Marp Markdown document (front-matter + global style)."""
    front = ["marp: true", "paginate: true"]
    math = config.reveal.math
    if math:
        front.append(f"math: {'mathjax' if math == 'mathjax' else 'katex'}")

    style = (
        "<style>\n"
        f"section {{ width: {theme.width}px; height: {theme.height}px; }}\n"
        f"{theme.css}\n"
        "</style>"
    )
    body = "\n\n---\n\n".join(slides)
    return "---\n" + "\n".join(front) + "\n---\n\n" + style + "\n\n" + body + "\n"


class MarpRenderer:
    name = "marp"

    def available(self) -> bool:
        return tool_available(BINARY)

    def capabilities(self) -> Caps:
        # Marp renders raw HTML in its HTML output but flattens it for pdf/pptx;
        # interactive embeds aren't a goal here, so embeds stays off.
        return Caps(html=True, pdf=True, pptx=True, embeds=False)

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
            lowered = scan_slide(group, resolver, deck.root, incremental="degrade")
            warnings.extend(lowered.warnings)
            slides.append(_format_slide(lowered, warnings))

        source = build_source(config, theme, slides)
        src_path = out_dir / "deck.marp.md"
        src_path.write_text(source, encoding="utf-8")

        out_name, fmt_flag = _FORMATS[fmt]
        output = out_dir / out_name
        # ``--html`` allows raw HTML in the source; ``--allow-local-files`` lets the
        # headless browser (pdf/pptx) read copied assets off disk.
        cmd = [
            BINARY,
            src_path.name,
            "-o",
            output.name,
            "--html",
            "--allow-local-files",
        ]
        if fmt_flag:
            cmd.append(fmt_flag)
        cmd.extend(_passthrough(config.marp))
        run_tool(cmd, cwd=out_dir, tool="marp-cli")

        return RenderResult(output=output, assets=resolver.copied, warnings=warnings)


def _passthrough(marp_cfg: dict) -> list[str]:
    """Turn the ``[marp]`` config table into extra ``marp-cli`` flags.

    ``key = true`` → ``--key``; ``key = "v"`` / ``key = 1`` → ``--key v``;
    ``key = false`` is dropped. Underscores in keys become dashes.
    """
    flags: list[str] = []
    for key, value in marp_cfg.items():
        flag = f"--{str(key).replace('_', '-')}"
        if value is True:
            flags.append(flag)
        elif value is False or value is None:
            continue
        else:
            flags.extend([flag, str(value)])
    return flags


register(MarpRenderer())

"""Orchestrate the PDF export: master (cached) → impose → grayscale → write.

``build_pdf`` is what the reveal adapter calls for ``-f pdf``. The slow part — the
Chromium master render — is content-hashed and cached under the deck's
``build_dir`` (so ``lectern clean`` of the ``out_dir`` keeps it; ``clean --all``
drops it), so re-exporting the same deck at a different ``layout`` or in B&W
re-runs only the cheap imposition / conversion, never Chromium
(``PDF-EXPORT.md`` § Caching).
"""

from __future__ import annotations

import datetime
import hashlib
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..assets import AssetResolver
from ..render.base import RenderResult
from ..render.lowering import is_blank_group, scan_slide
from ..theming import build_theme
from . import impose as _impose
from . import master as _master
from . import options as _options
from . import posters as _posters
from . import printcss as _printcss

if TYPE_CHECKING:
    from ..config import Config
    from ..preprocess import AssembledDeck

_CACHE_DIR = ".lectern-cache"


def _cache_dir(root: Path, config: Config) -> Path:
    """The PDF master cache, kept under the deck's ``build_dir`` (a reusable
    cache) so cleaning the ``out_dir`` doesn't discard it — only ``clean --all``
    (which removes ``build_dir``) does. Resolves like every deck path: relative
    to the deck root, absolute/``~`` pass through."""
    build = Path(config.build_dir).expanduser()
    return (build if build.is_absolute() else root / build) / _CACHE_DIR


def _slide_notes(
    deck: AssembledDeck, config: Config, work_dir: Path
) -> list[list[str]]:
    """Per-(non-blank)-slide speaker notes, aligned 1:1 with the master pages."""
    warnings: list[str] = []
    resolver = AssetResolver(deck.root, config.asset_base, work_dir, warnings)
    notes: list[list[str]] = []
    for group in deck.slides():
        if is_blank_group(group):
            continue
        lowered = scan_slide(group, resolver, deck.root, incremental="fragment")
        notes.append(lowered.notes)
    return notes


def _render_master(
    deck: AssembledDeck,
    config: Config,
    opts: _options.PdfOptions,
    work_dir: Path,
    warnings: list[str],
) -> bytes:
    """Build the print HTML and render (or reuse a cached) 1-up vector master."""
    from ..render.reveal import build_html

    theme = build_theme(config.theme, config.aspect, deck.root, deck.theme_dirs)
    print_css = _printcss.build(opts, theme.css)
    extra_head = f'<style id="lectern-print">\n{print_css}</style>' if print_css else ""
    # Notes layouts need exactly one master page per slide so notes map 1:1.
    steps = opts.fragments == "steps" and opts.layout == "1up"
    init_extra = {
        "pdfSeparateFragments": steps,
        "controls": False,
        "progress": False,
        "slideNumber": False,
    }
    html_text, _resolver, _theme = build_html(
        deck, config, work_dir, warnings, init_extra=init_extra, extra_head=extra_head
    )
    (work_dir / "index.html").write_text(html_text, encoding="utf-8")

    # Cache the master on everything that changes the master file (not the layout;
    # `tagged` adds a structure tree, so it keys a distinct master).
    key = hashlib.sha256(
        f"{html_text}|bg={opts.backgrounds}|steps={steps}|tagged={opts.tagged}".encode()
    ).hexdigest()[:16]
    cache_dir = _cache_dir(deck.root, config)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"master-{key}.pdf"
    if cached.is_file():
        return cached.read_bytes()

    _master.ensure_available()

    def prepare(page):
        _posters.capture_into(page, opts, config.pdf.poster_at, warnings)

    data = _master.print_to_pdf(
        work_dir / "index.html",
        print_background=opts.backgrounds,
        prepare=prepare if opts.posters != "off" else None,
        tagged=opts.tagged,
    )
    cached.write_bytes(data)
    return data


def build_pdf(deck: AssembledDeck, config: Config, out_dir: Path) -> RenderResult:
    """Assemble → master → impose → (grayscale) → ``out_dir/index.pdf``."""
    opts = _options.resolve(config.pdf)
    out_dir.mkdir(parents=True, exist_ok=True)
    warnings = list(deck.warnings)

    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        work_dir = Path(tmp)
        master_pdf = _render_master(deck, config, opts, work_dir, warnings)
        notes = _slide_notes(deck, config, work_dir)

    title = config.title or "Lectern deck"
    final = _impose.impose(
        master_pdf,
        options=opts,
        notes=notes,
        title=title,
        date=datetime.date.today().isoformat(),
        lang=config.lang,
    )

    if opts.bw and opts.bw_engine == "ghostscript":
        from . import grayscale

        if grayscale.available():
            final = grayscale.to_grayscale(final)
        else:
            warnings.append(
                "pdf: bw_engine='ghostscript' but the 'gs' binary is not on PATH; "
                "output left in color (use bw_engine='tokens' for vector B&W)"
            )

    output = out_dir / "index.pdf"
    output.write_bytes(final)
    return RenderResult(output=output, assets=[], warnings=warnings)

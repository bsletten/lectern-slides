"""The ``lectern`` command-line interface.

Commands so far:

* ``lectern assemble SOURCE [-o OUT]`` — expand includes/ranges into one deck and
  write the assembled Markdown (the "assemble then feed any renderer" escape
  hatch). Provenance comments are kept so the output is self-describing.
* ``lectern check SOURCE`` — validate includes/ranges (and surface warnings)
  without writing anything.
* ``lectern build SOURCE [-f html|pdf|pptx]`` — assemble and render to ``out_dir``
  via the configured adapter (reveal/remark are native HTML; marp/quarto shell out
  to their binaries — marp also does pdf/pptx). The requested format is gated by
  the adapter's capabilities, with a hint toward an adapter that supports it.
* ``lectern watch SOURCE`` — serve a live, reloading preview.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from . import __version__
from .config import resolve_source
from .errors import ConfigError, LecternError
from .preprocess import assemble, assemble_resolved
from .render import (
    FORMATS,
    get_renderer,
    renderers_supporting,
    supports_format,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Assemble Markdown slide sources into a deck and render it.",
)


def _fail(error: LecternError) -> typer.Exit:
    typer.secho(f"error: {error.render()}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


def _emit_warnings(warnings: list[str]) -> None:
    for w in warnings:
        typer.secho(f"warning: {w}", fg=typer.colors.YELLOW, err=True)


@app.command(name="assemble")
def assemble_cmd(
    source: Path = typer.Argument(
        ..., metavar="SOURCE", help="Manifest, deck dir, or .md file."
    ),
    out: Path | None = typer.Option(
        None, "-o", "--out", help="Write assembled Markdown here (default: stdout)."
    ),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Expand includes/ranges/partials into a single assembled deck."""
    try:
        deck = assemble(source, config_override=config)
    except LecternError as e:
        raise _fail(e) from None

    _emit_warnings(deck.warnings)
    text = deck.markdown(provenance=True)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        typer.secho(
            f"assembled {deck.slide_count} slide(s) -> {out}",
            fg=typer.colors.GREEN,
            err=True,
        )
    else:
        sys.stdout.write(text)


@app.command()
def check(
    source: Path = typer.Argument(
        ..., metavar="SOURCE", help="Manifest, deck dir, or .md file."
    ),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Validate includes, ranges, and partials without rendering."""
    try:
        deck = assemble(source, config_override=config)
    except LecternError as e:
        raise _fail(e) from None

    _emit_warnings(deck.warnings)
    suffix = " with warnings" if deck.warnings else ""
    typer.secho(
        f"ok: {deck.slide_count} slide(s) assembled cleanly{suffix}",
        fg=typer.colors.GREEN,
    )


@app.command()
def build(
    source: Path = typer.Argument(
        ..., metavar="SOURCE", help="Manifest, deck dir, or .md file."
    ),
    renderer: str | None = typer.Option(
        None, "-r", "--renderer", help="Override the renderer (e.g. reveal)."
    ),
    theme: str | None = typer.Option(
        None, "-t", "--theme", help="Override the theme (bundled name or path)."
    ),
    asset_base: str | None = typer.Option(
        None, "--asset-base", help="Override the asset base (local dir or URL)."
    ),
    out: Path | None = typer.Option(
        None,
        "-o",
        "--out",
        help="Override the output directory (default: deck out_dir).",
    ),
    fmt: str = typer.Option(
        "html", "-f", "--format", help="Output format: html | pdf | pptx."
    ),
    layout: str | None = typer.Option(
        None,
        "--layout",
        help="PDF layout: 1up | 2up | 2up-notes | 4up | 6up | 3up-notes.",
    ),
    bw: bool = typer.Option(False, "--bw", help="PDF: grayscale output."),
    backgrounds: bool | None = typer.Option(
        None, "--backgrounds/--no-backgrounds", help="PDF: keep slide backgrounds."
    ),
    light_inverse: bool = typer.Option(
        False, "--light-inverse", help="PDF: flip dark slides to light for ink economy."
    ),
    ink_saver: bool = typer.Option(
        False, "--ink-saver", help="PDF: bw + no backgrounds + light inverse."
    ),
    paper: str | None = typer.Option(
        None, "--paper", help="PDF paper: deck | letter | a4 | WxH."
    ),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Assemble and render the deck into the deck's output dir."""
    pdf_over: dict = {}
    if layout is not None:
        pdf_over["layout"] = layout
    if bw:
        pdf_over["color"] = "bw"
    if backgrounds is not None:
        pdf_over["backgrounds"] = backgrounds
    if light_inverse:
        pdf_over["light_inverse"] = True
    if ink_saver:
        pdf_over["ink_saver"] = True
    if paper is not None:
        pdf_over["paper"] = paper

    overrides = {
        "renderer": renderer,
        "theme": theme,
        "asset_base": asset_base,
        "out_dir": str(out) if out is not None else None,
        "pdf": pdf_over or None,
    }
    try:
        if fmt not in FORMATS:
            raise ConfigError(
                f"unknown output format '{fmt}' (expected one of: {', '.join(FORMATS)})"
            )
        resolved = resolve_source(
            source, config_override=config, cli_overrides=overrides
        )
        adapter = get_renderer(resolved.config.renderer)
        if not supports_format(adapter.capabilities(), fmt):
            alt = renderers_supporting(fmt)
            hint = f" (try renderer: {', '.join(alt)})" if alt else ""
            raise ConfigError(f"renderer '{adapter.name}' cannot produce '{fmt}'{hint}")
        if not adapter.available():
            raise ConfigError(
                f"renderer '{adapter.name}' is not available "
                "(its external tool is not installed or not on PATH)"
            )

        deck = assemble_resolved(resolved)
        result = adapter.render(deck, resolved.config, resolved.out_dir, fmt)
    except LecternError as e:
        raise _fail(e) from None

    _emit_warnings(result.warnings)
    typer.secho(
        f"built {deck.slide_count} slide(s), {len(result.assets)} asset(s) "
        f"-> {result.output}",
        fg=typer.colors.GREEN,
    )


@app.command()
def watch(
    source: Path = typer.Argument(
        ..., metavar="SOURCE", help="Manifest, deck dir, or .md file."
    ),
    host: str | None = typer.Option(None, "--host", help="Bind host."),
    port: int | None = typer.Option(None, "--port", help="Bind port."),
    open_browser: bool | None = typer.Option(
        None, "--open/--no-open", help="Open a browser on start."
    ),
    coi: bool | None = typer.Option(
        None, "--coi/--no-coi", help="Send COOP/COEP isolation headers."
    ),
    theme: str | None = typer.Option(
        None, "-t", "--theme", help="Override the theme (bundled name or path)."
    ),
    asset_base: str | None = typer.Option(
        None, "--asset-base", help="Override the asset base (local dir or URL)."
    ),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Serve a live, reloading preview that rebuilds on source changes."""
    from .serve import LiveReloadServer, watch_paths

    overrides = {"theme": theme, "asset_base": asset_base}
    try:
        resolved = resolve_source(
            source, config_override=config, cli_overrides=overrides
        )
        # Surface a config/render error immediately rather than after the server
        # is up (the running server then shows build errors as an overlay).
        get_renderer(resolved.config.renderer)
    except LecternError as e:
        raise _fail(e) from None

    serve_cfg = resolved.config.serve
    server = LiveReloadServer(
        source,
        out_dir=resolved.out_dir,
        host=host or serve_cfg.host,
        port=port or serve_cfg.port,
        coi=serve_cfg.coi if coi is None else coi,
        open_browser=serve_cfg.open if open_browser is None else open_browser,
        config_override=config,
        cli_overrides=overrides,
        watch=watch_paths(resolved),
    )
    server.run()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"lectern {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    pass


if __name__ == "__main__":
    app()

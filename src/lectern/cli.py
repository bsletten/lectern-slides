"""The ``lectern`` command-line interface.

M1 ships two commands:

* ``lectern assemble SOURCE [-o OUT]`` — expand includes/ranges into one deck and
  write the assembled Markdown (the "assemble then feed any renderer" escape
  hatch). Provenance comments are kept so the output is self-describing.
* ``lectern check SOURCE`` — validate includes/ranges (and surface warnings)
  without writing anything.

Rendering, watch/serve, and the other adapters arrive in later milestones.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from . import __version__
from .errors import LecternError
from .preprocess import assemble

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

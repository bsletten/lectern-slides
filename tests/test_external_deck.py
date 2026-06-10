"""Regression: a deck lives in its own repo, fully external to this tool.

Build a deck in a temp dir (outside the project tree) with relative slides, a
partial resolved via a search path, and an asset — then run from a *different*
CWD and assert everything resolves against the deck root, artifacts land in the
deck's own tree, and nothing leaks into the CWD.
"""

from pathlib import Path

from conftest import write
from typer.testing import CliRunner

from lectern.cli import app
from lectern.config import resolve_source
from lectern.preprocess import assemble, assemble_resolved
from lectern.render import get_renderer

runner = CliRunner()


def _make_deck(deck: Path) -> None:
    write(
        deck,
        "deck.toml",
        'title = "External"\n'
        'partials = ["./_partials"]\n'
        'asset_base = "./assets"\n'
        'slides = ["slides/a.md", "slides/b.md"]\n',
    )
    write(
        deck,
        "slides/a.md",
        "<!-- slide: .center -->\n\n# A\n\n<!-- include: shared.md -->\n",
    )
    write(deck, "slides/b.md", "# B\n\n![pic](pic.png)\n")
    write(deck, "_partials/shared.md", "shared partial body")
    write(deck, "assets/pic.png", "PNGDATA")


def test_build_external_deck_from_other_cwd(tmp_path_factory, monkeypatch):
    deck = tmp_path_factory.mktemp("external-deck")
    other_cwd = tmp_path_factory.mktemp("elsewhere")
    _make_deck(deck)

    # Crucial: run from an unrelated directory with an absolute SOURCE.
    monkeypatch.chdir(other_cwd)

    resolved = resolve_source(deck)
    # out_dir defaults to dist *inside the deck root*, not the CWD.
    assert resolved.out_dir == deck.resolve() / "dist"

    deckobj = assemble_resolved(resolved)
    adapter = get_renderer(resolved.config.renderer)
    result = adapter.render(deckobj, resolved.config, resolved.out_dir)

    html = result.output.read_text(encoding="utf-8")
    assert result.output == deck.resolve() / "dist" / "index.html"
    assert "shared partial body" in html  # partial found via deck-root search path
    assert "assets/pic-" in html  # asset rewritten
    assert (deck / "dist" / "assets").is_dir()  # asset copied into deck's tree

    # Nothing was written under the unrelated CWD.
    assert not (other_cwd / "dist").exists()
    assert list(other_cwd.iterdir()) == []


def test_cli_build_external_deck_from_other_cwd(tmp_path_factory, monkeypatch):
    deck = tmp_path_factory.mktemp("external-deck-cli")
    other_cwd = tmp_path_factory.mktemp("elsewhere-cli")
    _make_deck(deck)
    monkeypatch.chdir(other_cwd)

    result = runner.invoke(app, ["build", str(deck)])
    assert result.exit_code == 0, result.output
    assert (deck / "dist" / "index.html").is_file()
    assert not (other_cwd / "dist").exists()


def test_include_resolver_keys_off_deck_root_not_cwd(tmp_path_factory, monkeypatch):
    # M1 sanity: assemble (no render) must resolve includes against the deck root
    # even when invoked from elsewhere with an absolute source.
    deck = tmp_path_factory.mktemp("assemble-deck")
    elsewhere = tmp_path_factory.mktemp("away")
    write(deck, "main.md", "# Main\n\n<!-- include: sibling.md -->\n")
    write(deck, "sibling.md", "sibling content")
    monkeypatch.chdir(elsewhere)

    out = assemble(deck / "main.md").markdown()
    assert "sibling content" in out

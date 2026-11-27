"""`[reveal] assets`: cdn (default) · vendored · local — a deck that loads nothing
from another host, and the refusals for what it cannot yet self-host."""

import re
import shutil
from importlib import resources
from pathlib import Path

import pytest
from conftest import write
from typer.testing import CliRunner

from lectern.cli import app
from lectern.config import resolve_source
from lectern.errors import ConfigError
from lectern.preprocess import assemble_resolved
from lectern.render import get_renderer
from lectern.render.reveal_assets import REVEAL_CDN, remote_loads
from lectern.source import FilesystemSource

runner = CliRunner()
VENDORED = Path(str(resources.files("lectern") / "vendor" / "reveal.js"))
_LOAD = re.compile(r'<(?:script|link)\b[^>]*\s(?:src|href)="([^"]+)"')
_HASHED = re.compile(r"^assets/[\w.-]+-[0-9a-f]{8}\.(?:js|css)$")


def _deck(tmp_path, reveal: str = "", body: str = "# Hi\n\n```py\nx = 1\n```\n"):
    deck = tmp_path / "deck"
    write(deck, "deck.toml", f'slides = ["main.md"]\n\n[reveal]\n{reveal}')
    write(deck, "main.md", body)
    return deck


def _build(deck_dir, out, fmt="html", **overrides):
    resolved = resolve_source(deck_dir, cli_overrides=overrides or None)
    deck = assemble_resolved(resolved)
    return get_renderer("reveal").render(deck, resolved.config, out, fmt)


def _assert_self_contained(result):
    html = result.output.read_text(encoding="utf-8")
    assert remote_loads(html) == []
    assert "cdn.jsdelivr" not in html
    loads = _LOAD.findall(html)
    assert loads, "the page loads reveal from somewhere"
    for href in loads:
        assert _HASHED.match(href), href
        assert (result.output.parent / href).is_file(), href
    return html, loads


# --------------------------------------------------------------------------- #
# cdn — the default, unchanged
# --------------------------------------------------------------------------- #
def test_cdn_default_and_explicit_cdn_are_byte_identical_to_main(fixtures, tmp_path):
    # The golden was built from main before `[reveal] assets` existed.
    golden = (fixtures / "golden" / "render-deck.index.html").read_bytes()
    default = _build(fixtures / "render-deck", tmp_path / "a")
    assert default.output.read_bytes() == golden
    explicit = _build(
        fixtures / "render-deck", tmp_path / "b", reveal={"assets": "cdn"}
    )
    assert explicit.output.read_bytes() == golden
    assert f"{REVEAL_CDN}/dist/reveal.js" in golden.decode()


# --------------------------------------------------------------------------- #
# vendored
# --------------------------------------------------------------------------- #
def test_vendored_copy_ships_with_its_license_and_notice():
    assert "Hakim El Hattab" in (VENDORED / "LICENSE").read_text()
    notice = (VENDORED / "NOTICE.md").read_text()
    assert "reveal.js-5.1.0.tgz" in notice and "sha512-" in notice


def test_vendored_deck_loads_nothing_from_another_host(tmp_path):
    result = _build(_deck(tmp_path, 'assets = "vendored"\n'), tmp_path / "dist")
    html, loads = _assert_self_contained(result)
    names = [Path(h).name for h in loads]
    for stem in ("reset", "reveal", "markdown", "notes", "highlight"):
        assert any(n.startswith(f"{stem}-") for n in names), stem
    # the copied bytes are the vendored files, unmodified
    js = next(h for h in loads if Path(h).name.startswith("reveal-") and ".js" in h)
    assert (result.output.parent / js).read_bytes() == (
        VENDORED / "dist" / "reveal.js"
    ).read_bytes()


def test_vendored_without_highlight_omits_the_plugin(tmp_path):
    deck = _deck(tmp_path, 'assets = "vendored"\nhighlight = false\n')
    _, loads = _assert_self_contained(_build(deck, tmp_path / "dist"))
    assert not any("highlight" in h for h in loads)


def test_vendored_rebuild_keeps_reveal_in_assets(tmp_path):
    deck = _deck(tmp_path, 'assets = "vendored"\n')
    _build(deck, tmp_path / "dist")
    again = _build(deck, tmp_path / "dist")
    assert again.pruned == 0
    _assert_self_contained(again)


# --------------------------------------------------------------------------- #
# local
# --------------------------------------------------------------------------- #
def _local_deck(tmp_path, path='"vendor/reveal"'):
    deck = _deck(tmp_path, f'assets = "local"\npath = {path}\n')
    shutil.copytree(VENDORED, deck / "vendor" / "reveal")
    return deck


def test_local_deck_loads_nothing_from_another_host(tmp_path):
    _assert_self_contained(_build(_local_deck(tmp_path), tmp_path / "dist"))


def test_local_files_are_read_through_the_decks_source(tmp_path):
    reads = []

    class Recording(FilesystemSource):
        def read_bytes(self, key):
            reads.append(Path(key))
            return super().read_bytes(key)

    deck_dir = _local_deck(tmp_path)
    resolved = resolve_source(deck_dir)
    deck = assemble_resolved(resolved)
    deck.source = Recording()
    get_renderer("reveal").render(deck, resolved.config, tmp_path / "dist")
    assert deck_dir / "vendor" / "reveal" / "dist" / "reveal.js" in reads


def test_local_path_edits_show_up_in_the_build(tmp_path):
    deck = _local_deck(tmp_path)
    (deck / "vendor" / "reveal" / "dist" / "reveal.js").write_text("/* mine */")
    result = _build(deck, tmp_path / "dist")
    _, loads = _assert_self_contained(result)
    js = next(h for h in loads if Path(h).name.startswith("reveal-") and ".js" in h)
    assert (result.output.parent / js).read_text() == "/* mine */"


def test_local_without_path_is_refused(tmp_path):
    deck = _deck(tmp_path, 'assets = "local"\n')
    with pytest.raises(ConfigError, match=r'assets = "local" needs \[reveal\] path'):
        _build(deck, tmp_path / "dist")


def test_local_missing_directory_is_refused(tmp_path):
    deck = _deck(tmp_path, 'assets = "local"\npath = "nowhere"\n')
    with pytest.raises(ConfigError, match=r'path "nowhere" holds no reveal.js files'):
        _build(deck, tmp_path / "dist")


def test_local_incomplete_directory_names_what_is_missing(tmp_path):
    deck = _local_deck(tmp_path)
    (deck / "vendor" / "reveal" / "plugin" / "notes" / "notes.js").unlink()
    (deck / "vendor" / "reveal" / "plugin" / "highlight" / "highlight.js").unlink()
    with pytest.raises(ConfigError) as e:
        _build(deck, tmp_path / "dist")
    assert str(e.value) == (
        '[reveal] path "vendor/reveal" is missing plugin/notes/notes.js, '
        "plugin/highlight/highlight.js, which this deck needs from reveal.js"
    )


# --------------------------------------------------------------------------- #
# refusals of what is still CDN-only
# --------------------------------------------------------------------------- #
def test_unknown_mode_is_refused(tmp_path):
    deck = _deck(tmp_path, 'assets = "offline"\n')
    with pytest.raises(ConfigError, match=r'assets = "offline" is not a mode'):
        _build(deck, tmp_path / "dist")
    r = runner.invoke(app, ["check", str(deck)])
    assert r.exit_code != 0 and "is not a mode" in r.output


@pytest.mark.parametrize("mode", ["vendored", "local"])
@pytest.mark.parametrize(
    ("extra", "body", "match"),
    [
        ('math = "katex"\n', "# Hi\n", "cannot render math"),
        ("", "# Hi\n\n```mermaid\ngraph LR; a-->b\n```\n", "cannot render Mermaid"),
        ("mermaid = true\n", "# Hi\n", "cannot render Mermaid"),
    ],
)
def test_cdn_only_features_are_refused(tmp_path, mode, extra, body, match):
    deck = _deck(tmp_path, f'assets = "{mode}"\npath = "vendor/reveal"\n{extra}', body)
    shutil.copytree(VENDORED, deck / "vendor" / "reveal")
    with pytest.raises(ConfigError, match=match):
        _build(deck, tmp_path / "dist")


def test_free_font_awesome_kit_is_refused(tmp_path):
    deck = _deck(tmp_path, 'assets = "vendored"\n')
    toml = deck / "deck.toml"
    toml.write_text("font_awesome = true\n" + toml.read_text())
    with pytest.raises(ConfigError, match="font_awesome = true"):
        _build(deck, tmp_path / "dist")


# --------------------------------------------------------------------------- #
# lectern check flags a remaining remote load
# --------------------------------------------------------------------------- #
def test_check_passes_a_clean_vendored_deck(tmp_path):
    r = runner.invoke(app, ["check", str(_deck(tmp_path, 'assets = "vendored"\n'))])
    assert r.exit_code == 0, r.output
    assert "another host" not in r.output


def test_check_flags_a_remote_image_in_a_vendored_deck(tmp_path):
    deck = _deck(
        tmp_path,
        'assets = "vendored"\n',
        "# Hi\n\n![a chart](https://example.com/chart.png)\n",
    )
    r = runner.invoke(app, ["check", str(deck)])
    assert (
        'a11y: [reveal] assets = "vendored", but the built deck loads '
        "https://example.com/chart.png from another host"
    ) in r.output


def test_remote_loads_scan():
    html = (
        '<link rel="stylesheet" href="https://a.example/x.css">'
        '<script src="//b.example/y.js"></script>'
        "<script type=\"module\">import m from 'https://c.example/m.mjs';</script>"
        "<style>@font-face { src: url(https://d.example/f.woff2); }</style>"
        '<a href="https://not-a-load.example/">link</a>'
        '<script src="assets/reveal-0123abcd.js"></script>'
    )
    assert remote_loads(html) == [
        "https://a.example/x.css",
        "//b.example/y.js",
        "https://c.example/m.mjs",
        "https://d.example/f.woff2",
    ]


# --------------------------------------------------------------------------- #
# in the browser, and the PDF master (skip without Playwright + Chromium)
# --------------------------------------------------------------------------- #
def _chromium_available() -> bool:
    try:
        from lectern.pdf.master import ensure_available

        ensure_available()
        return True
    except Exception:
        return False


needs_chromium = pytest.mark.skipif(
    not _chromium_available(), reason="Chromium/Playwright not installed"
)


@needs_chromium
@pytest.mark.parametrize("mode", ["vendored", "local"])
def test_browser_requests_nothing_from_another_host(tmp_path, mode):
    from lectern.a11y import audit_built

    deck = _local_deck(tmp_path) if mode == "local" else _deck(tmp_path, "")
    if mode == "vendored":
        (deck / "deck.toml").write_text(
            'slides = ["main.md"]\n\n[reveal]\nassets = "vendored"\n'
        )
    result = _build(deck, tmp_path / "dist")
    assert audit_built(result.output, [], flag_remote=True) == []


@needs_chromium
def test_browser_audit_flags_a_remote_request(tmp_path):
    from lectern.a11y import audit_built

    deck = _deck(
        tmp_path,
        'assets = "vendored"\n',
        '# Hi\n\n<img alt="x" src="http://127.0.0.2:9/nope.png">\n',
    )
    result = _build(deck, tmp_path / "dist")
    assert audit_built(result.output, [], flag_remote=True) == [
        "the built deck loaded http://127.0.0.2:9/nope.png from another host"
    ]


@needs_chromium
@pytest.mark.parametrize("mode", ["vendored", "local"])
def test_pdf_builds_from_the_local_copy(tmp_path, mode):
    deck = _local_deck(tmp_path)
    if mode == "vendored":
        (deck / "deck.toml").write_text(
            'slides = ["main.md"]\n\n[reveal]\nassets = "vendored"\n'
        )
    result = _build(
        deck,
        tmp_path / "dist",
        "pdf",
        pdf={"layout": "1up"},
        build_dir=str(tmp_path / "build"),
    )
    assert result.output.suffix == ".pdf"
    assert result.output.read_bytes().startswith(b"%PDF")

"""`[fences]`: a configured code fence renders as a custom element.

The element and its files come from the deck (here the generic ``demo-cell`` in
``fixtures/fence-deck``); lectern hard-codes no element.
"""

import re
import shutil

import pytest
from conftest import write
from test_pdf import HAVE_CHROMIUM
from typer.testing import CliRunner

from lectern.cli import app
from lectern.config import resolve_source
from lectern.errors import ConfigError
from lectern.fences import render_element
from lectern.preprocess import assemble_resolved
from lectern.render import get_renderer

runner = CliRunner()


def _build(deck_dir, out):
    resolved = resolve_source(deck_dir)
    deck = assemble_resolved(resolved)
    return get_renderer("reveal").render(deck, resolved.config, out, "html")


def _copy_deck(fixtures, tmp_path):
    deck = tmp_path / "deck"
    shutil.copytree(fixtures / "fence-deck", deck)
    return deck


# --------------------------------------------------------------------------- #
# lowering (pure)
# --------------------------------------------------------------------------- #
def test_render_element_escapes_and_keeps_blank_lines_in_one_block():
    lines = render_element("x-cell", ["a < b && c", "", "</script> </x-cell>"])
    assert lines == [
        '<div class="lectern-fence"><x-cell>a &lt; b &amp;&amp; c&#10;&#10;'
        "&lt;/script&gt; &lt;/x-cell&gt;</x-cell></div>",
        "",
    ]


def test_render_element_strips_the_opening_fences_indentation():
    lines = render_element("x-cell", ["  a", "    b", " c", "", "d"], "  ")
    assert lines == [
        '  <div class="lectern-fence">'
        "<x-cell>a&#10;  b&#10;c&#10;&#10;d</x-cell></div>",
        "",
    ]


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def test_fence_builds_as_element_with_assets_in_place(fixtures, tmp_path):
    out = tmp_path / "dist"
    result = _build(fixtures / "fence-deck", out)
    html = result.output.read_text(encoding="utf-8")

    assert (
        '<div class="lectern-fence"><demo-cell>source a &lt; b &amp; "c"&#10;&#10;'
        "sink urn:deck:note</demo-cell></div>" in html
    )
    # Other fences render exactly as before: a plain fence in the markdown.
    assert '```python\nprint("an ordinary fence")\n```' in html

    # Every named file lands, unrenamed, in one content-hashed assets/ subdir...
    dirs = [p for p in (out / "assets").iterdir() if p.is_dir()]
    assert len(dirs) == 1 and dirs[0].name.startswith("demo-cell-")
    names = sorted(p.name for p in dirs[0].iterdir())
    assert names == ["demo-cell.css", "demo-cell.js", "demo-glue.js", "demo-kernel.bin"]
    for name in names:
        src = fixtures / "fence-deck" / "vendor" / name
        assert (dirs[0] / name).read_bytes() == src.read_bytes()

    # ...loaded once in <head> by a relative URL, never a CDN.
    rel = f"assets/{dirs[0].name}"
    head = html.split("</head>")[0]
    assert head.count(f'<script type="module" src="{rel}/demo-cell.js"></script>') == 1
    assert head.count(f'<link rel="stylesheet" href="{rel}/demo-cell.css">') == 1
    kernel = (fixtures / "fence-deck" / "kernel.json").read_text().rstrip("\n")
    assert f'<script type="application/demo-kernel+json">\n{kernel}\n</script>' in head
    assert set(result.assets) >= {dirs[0] / n for n in names}


def test_fence_in_a_list_item_loses_the_list_indentation(fixtures, tmp_path):
    deck = _copy_deck(fixtures, tmp_path)
    (deck / "slides.md").write_text(
        "# Listed\n\n- a step\n\n  ```demo\n  source x\n    indented\n  ```\n"
    )
    html = _build(deck, tmp_path / "dist").output.read_text(encoding="utf-8")
    assert (
        '  <div class="lectern-fence"><demo-cell>source x&#10;  indented'
        "</demo-cell></div>" in html
    )


def test_asset_hrefs_are_percent_encoded(fixtures, tmp_path):
    deck = _copy_deck(fixtures, tmp_path)
    vendor = deck / "vendor"
    (vendor / "demo-cell.js").rename(vendor / "demo cell#1%.js")
    (vendor / "demo-cell.css").rename(vendor / "demo cell#1%.css")
    toml = deck / "deck.toml"
    toml.write_text(
        toml.read_text()
        .replace("vendor/demo-cell.js", "vendor/demo cell#1%.js")
        .replace("vendor/demo-cell.css", "vendor/demo cell#1%.css")
    )
    out = tmp_path / "dist"
    html = _build(deck, out).output.read_text(encoding="utf-8")
    (d,) = [p for p in (out / "assets").iterdir() if p.is_dir()]
    assert (d / "demo cell#1%.js").is_file() and (d / "demo cell#1%.css").is_file()
    rel = f"assets/{d.name}"
    assert f'<script type="module" src="{rel}/demo%20cell%231%25.js"></script>' in html
    assert f'<link rel="stylesheet" href="{rel}/demo%20cell%231%25.css">' in html


def test_fence_files_are_read_through_the_decks_source(fixtures, tmp_path):
    """A deck served by a non-filesystem Source (KernelSource) with [fences]."""
    from test_source import KROOT, _kernel_from_dir

    from lectern.source import FilesystemSource

    disk = fixtures / "fence-deck"
    kernel = _kernel_from_dir(disk)

    def build(root, src, out):
        resolved = resolve_source(root, src=src)
        deck = assemble_resolved(resolved, src=src)
        return get_renderer("reveal").render(deck, resolved.config, out, "html")

    k = build(KROOT, kernel, tmp_path / "out-kernel")
    d = build(disk, FilesystemSource(), tmp_path / "out-disk")
    assert k.output.read_text(encoding="utf-8") == d.output.read_text(encoding="utf-8")

    def tree(out):
        return {
            p.relative_to(out).as_posix(): p.read_bytes()
            for p in (out / "assets").rglob("*")
            if p.is_file()
        }

    assert tree(tmp_path / "out-kernel") == tree(tmp_path / "out-disk")
    assert any(n.endswith("/demo-kernel.bin") for n in tree(tmp_path / "out-kernel"))


def test_rebuild_prunes_a_stale_fence_directory(fixtures, tmp_path):
    deck = _copy_deck(fixtures, tmp_path)
    out = tmp_path / "dist"
    _build(deck, out)
    (old,) = [p for p in (out / "assets").iterdir() if p.is_dir()]
    (deck / "vendor" / "demo-glue.js").write_text('export const runLabel = "Go";\n')
    result = _build(deck, out)
    (new,) = [p for p in (out / "assets").iterdir() if p.is_dir()]
    assert new != old and not old.exists()
    assert result.pruned == 4


def test_deck_without_fences_is_byte_identical(fixtures, tmp_path):
    # The golden was built from main before `[fences]` existed.
    result = _build(fixtures / "render-deck", tmp_path / "dist")
    golden = fixtures / "golden" / "render-deck.index.html"
    assert result.output.read_bytes() == golden.read_bytes()


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", ["scripts", "styles", "files"])
def test_a_url_is_refused_with_a_sentence(fixtures, tmp_path, key):
    deck = _copy_deck(fixtures, tmp_path)
    toml = deck / "deck.toml"
    text = re.sub(
        rf"^{key}\s*= \[",
        f'{key} = ["https://cdn.example.com/x.js", ',
        toml.read_text(),
        count=1,
        flags=re.M,
    )
    toml.write_text(text)
    msg = (
        f"fences.demo.{key}: 'https://cdn.example.com/x.js' is a URL; fence assets "
        "are copied into the build so a deck stays self-contained, so name a local "
        "file instead"
    )
    with pytest.raises(ConfigError) as e:
        _build(deck, tmp_path / "dist")
    assert str(e.value) == msg
    # `check` refuses it too, before anything is written.
    r = runner.invoke(app, ["check", str(deck)])
    assert r.exit_code != 0 and msg in " ".join(r.output.split())


def test_missing_file_and_bad_element_name_are_refused(fixtures, tmp_path):
    deck = _copy_deck(fixtures, tmp_path)
    (deck / "vendor" / "demo-glue.js").unlink()
    r = runner.invoke(app, ["check", str(deck)])
    assert r.exit_code != 0
    assert "fences.demo.files: file not found: vendor/demo-glue.js" in r.output

    write(tmp_path, "d2/deck.toml", '[fences.demo]\nelement = "democell"\n')
    write(tmp_path, "d2/a.md", "# A\n")
    with pytest.raises(ConfigError, match="not a custom-element name"):
        resolve_source(tmp_path / "d2")


def test_data_block_containing_end_script_is_refused(fixtures, tmp_path):
    deck = _copy_deck(fixtures, tmp_path)
    (deck / "kernel.json").write_text('{"x": "</SCRIPT>"}\n')
    with pytest.raises(ConfigError, match="fences.demo.data: the block contains"):
        _build(deck, tmp_path / "dist")


def test_data_block_containing_comment_open_is_refused(fixtures, tmp_path):
    deck = _copy_deck(fixtures, tmp_path)
    (deck / "kernel.json").write_text('{"x": "<!-- <script>"}\n')
    msg = (
        "fences.demo.data: the block contains '<!--', which can make the browser "
        "read past its '</script>' into the rest of the page; it is passed through "
        "untouched, so remove it"
    )
    with pytest.raises(ConfigError) as e:
        _build(deck, tmp_path / "dist")
    assert str(e.value) == msg
    r = runner.invoke(app, ["check", str(deck)])
    assert r.exit_code != 0 and msg in " ".join(r.output.split())


def test_check_passes_on_the_fixture(fixtures):
    r = runner.invoke(app, ["check", str(fixtures / "fence-deck")])
    assert r.exit_code == 0, r.output
    assert "ok: 2 slide(s)" in r.output


# --------------------------------------------------------------------------- #
# in the browser (skips without Playwright + Chromium)
# --------------------------------------------------------------------------- #
needs_chromium = pytest.mark.skipif(
    not HAVE_CHROMIUM, reason="Chromium/Playwright not installed"
)


@needs_chromium
def test_built_audit_passes_an_accessible_element(fixtures, tmp_path):
    from lectern.a11y import audit_built

    result = _build(fixtures / "fence-deck", tmp_path / "dist")
    assert audit_built(result.output, ["demo-cell"]) == []


@needs_chromium
def test_built_audit_flags_unnamed_run_and_missing_live_region(fixtures, tmp_path):
    from lectern.a11y import audit_built

    deck = _copy_deck(fixtures, tmp_path)
    js = deck / "vendor" / "demo-cell.js"
    js.write_text(
        js.read_text()
        .replace("button.textContent = runLabel;", "")
        .replace('output.setAttribute("aria-live", "polite");', "")
    )
    result = _build(deck, tmp_path / "dist")
    assert audit_built(result.output, ["demo-cell"]) == [
        "slide 1, <demo-cell> 1: 1 control(s) have no accessible name",
        "slide 1, <demo-cell> 1: its output is not a live region (aria-live / "
        'role="status"), so screen readers are not told of results',
    ]
    r = runner.invoke(app, ["check", str(deck), "--built"])
    assert "a11y: slide 1, <demo-cell> 1: 1 control(s) have no accessible name" in (
        r.output
    )


@needs_chromium
def test_element_gets_exact_code_and_keeps_its_keys_from_reveal(fixtures, tmp_path):
    import functools
    import http.server
    import threading

    from playwright.sync_api import sync_playwright

    from lectern.a11y import _QuietHandler

    result = _build(fixtures / "fence-deck", tmp_path / "dist")
    handler = functools.partial(_QuietHandler, directory=str(result.output.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
            page.wait_for_selector("demo-cell button")
            code = page.eval_on_selector("demo-cell", "el => el.dataset.code")
            assert code == 'source a < b & "c"\n\nsink urn:deck:note'
            try:  # reveal.js comes from its CDN; skip the key check offline
                page.wait_for_function(
                    "window.Reveal && Reveal.isReady()", timeout=8000
                )
            except Exception:
                pytest.skip("reveal.js could not load from its CDN")
            # Focus inside the cell: reveal never sees the arrow key.
            page.focus("demo-cell button")
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(300)
            assert page.evaluate("Reveal.getIndices().h") == 0
            # Focus outside it: the same key changes slides as usual.
            page.evaluate("document.activeElement.blur()")
            page.keyboard.press("ArrowRight")
            page.wait_for_function("Reveal.getIndices().h === 1", timeout=3000)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

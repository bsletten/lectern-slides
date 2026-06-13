"""Remark adapter: parity for legacy decks, lowering for neutral decks."""

from pathlib import Path

from lectern.config import resolve_source
from lectern.preprocess import assemble_resolved
from lectern.render import Caps, get_renderer
from lectern.render.remark import _reduced_ratio


def _render(source, out_dir: Path, **overrides):
    resolved = resolve_source(source, cli_overrides=overrides or None)
    deck = assemble_resolved(resolved)
    adapter = get_renderer("remark")
    result = adapter.render(deck, resolved.config, out_dir)
    return result.output.read_text(encoding="utf-8"), result


def test_remark_registered_with_caps():
    adapter = get_renderer("remark")
    assert adapter.name == "remark"
    assert adapter.available() is True
    assert adapter.capabilities() == Caps(html=True, pdf=False, pptx=False, embeds=True)


def test_reduced_ratio():
    assert _reduced_ratio(1280, 720) == "16:9"
    assert _reduced_ratio(1024, 768) == "4:3"


def test_legacy_deck_passes_native_syntax_through(fixtures, tmp_path):
    html, _ = _render(fixtures / "legacy-remark", tmp_path)
    # Injected layout template gives every slide the `slide` class.
    assert "layout: true" in html
    assert "class: slide" in html
    # Legacy syntax preserved verbatim for remark.js to interpret.
    assert "class: center, middle" in html
    assert "name: title" in html
    assert ".accent[A highlighted span]" in html
    assert "--" in html  # the increment separator survives
    assert "???" in html  # native speaker-notes marker survives
    assert "remarkjs.com" in html  # remark.js loaded


def test_neutral_directive_lowered_to_property_lines(fixtures, tmp_path):
    html, result = _render(fixtures / "render-deck", tmp_path)
    # `<!-- slide: .center .middle #hero data-x=1 -->` -> property lines.
    assert "class: center, middle" in html
    assert "name: hero" in html
    # Unsupported data attribute and incremental/math all degrade with warnings.
    assert any("data-x" in w for w in result.warnings)
    assert any("incremental" in w for w in result.warnings)
    assert any("math" in w for w in result.warnings)


def test_neutral_notes_become_triple_question(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert "???" in html
    assert "A speaker note for the builds slide." in html


def test_assets_resolved_and_copied(fixtures, tmp_path):
    html, result = _render(fixtures / "render-deck", tmp_path)
    assert "background-image: url(assets/grid-" in html
    assert (tmp_path / "assets").is_dir()
    assert result.assets


def test_script_close_escaped_in_source(tmp_path):
    from conftest import write

    write(tmp_path, "raw.md", "# Raw\n\n<script>x</script>\n")
    html, _ = _render(tmp_path / "raw.md", tmp_path / "out")
    assert "<\\/script>" in html  # ``</`` escaped so the bootstrap script is safe


def test_remark_mermaid_lowered_and_loaded(tmp_path):
    from conftest import write

    write(tmp_path, "deck.toml", 'slides = ["s.md"]\n')
    write(tmp_path, "s.md", "# Diagram\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
    html, _ = _render(tmp_path, tmp_path / "out")
    assert '<pre class="mermaid">' in html
    assert "A --> B" in html
    assert "mermaid.esm.min.mjs" in html

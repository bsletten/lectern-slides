"""Reveal adapter: structural assertions on the generated HTML (not pixels)."""

from pathlib import Path

from conftest import write

from lectern.config import resolve_source
from lectern.preprocess import assemble_resolved
from lectern.render import Caps, get_renderer


def _render(source, out_dir: Path, **overrides):
    resolved = resolve_source(source, cli_overrides=overrides or None)
    deck = assemble_resolved(resolved)
    adapter = get_renderer(resolved.config.renderer)
    result = adapter.render(deck, resolved.config, out_dir)
    return result.output.read_text(encoding="utf-8"), result


def test_reveal_registered_with_caps():
    adapter = get_renderer("reveal")
    assert adapter.name == "reveal"
    assert adapter.available() is True
    assert adapter.capabilities() == Caps(html=True, pdf=False, pptx=False, embeds=True)


def test_section_per_slide_with_classes_and_id(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert html.count("<section ") == 3
    assert '<section class="slide center middle" id="hero" data-x="1"' in html
    assert '<section class="slide inverse"' in html


def test_notes_lowered(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert "Note:\nA speaker note for the builds slide." in html


def test_incremental_items_get_fragment(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert html.count('<!-- .element: class="fragment" -->') == 2


def test_place_box_lowered_to_div(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert '<div class="place bottom right">' in html


def test_inline_span_lowered(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert '<span class="accent">highlighted span</span>' in html


def test_background_image_asset_resolved_on_section(fixtures, tmp_path):
    html, result = _render(fixtures / "render-deck", tmp_path)
    assert 'data-background-image="assets/grid-' in html
    assert (tmp_path / "assets").is_dir()
    names = {p.name for p in result.assets}
    assert any(n.startswith("grid-") for n in names)
    assert any(n.startswith("logo-") for n in names)


def test_aspect_drives_reveal_dimensions(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert '"width": 1024' in html and '"height": 768' in html  # 4:3


def test_math_and_highlight_plugins_wired(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert "plugin/math/math.js" in html
    assert "katex" in html
    assert "RevealMath.KaTeX" in html
    assert "plugin/highlight/highlight.js" in html


def test_script_tag_escaped_in_template(tmp_path):
    write(tmp_path, "raw.md", "# Raw\n\n<script>alert(1)</script>\n")
    html, _ = _render(tmp_path / "raw.md", tmp_path / "out")
    assert "<\\/script>" in html  # escaped so it can't close data-markdown early


def test_theme_css_and_layer_injected(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert 'id="lectern-theme"' in html
    assert 'id="lectern-layout"' in html
    assert "--slide-w: 1024px" in html  # aspect override present


def test_renderer_override_via_cli(fixtures, tmp_path):
    # An unknown renderer override surfaces as a clean error at lookup time.
    from lectern.errors import ConfigError

    resolved = resolve_source(
        fixtures / "render-deck", cli_overrides={"renderer": "reveal"}
    )
    assert resolved.config.renderer == "reveal"
    import pytest

    with pytest.raises(ConfigError):
        get_renderer("nope")

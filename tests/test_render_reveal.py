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
    assert adapter.capabilities() == Caps(html=True, pdf=True, pptx=False, embeds=True)


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


def test_on_dark_helper_forces_light_text(fixtures, tmp_path):
    # `.on-dark` forces light text/links over a dark backdrop, independent of a
    # theme's `.inverse` (which may be a light "moment" with dark text).
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert "section.slide.on-dark" in html
    assert "color: #f5f5f7 !important;" in html
    assert "text-shadow:" in html  # legibility over busy imagery
    # Regression: the section-level color rule must NOT also force `opacity: 1`
    # on the section — reveal animates section opacity for fade transitions, and
    # pinning it kept this slide visible as an off-screen neighbour (its text
    # flashed onto adjacent slides). The color block ends right after `color`.
    assert "color: #f5f5f7 !important;\n}" in html


def test_standalone_image_centered_and_height_capped(fixtures, tmp_path):
    # A Markdown image on its own line (a single-child <p>) is centered and
    # capped to a fraction of the slide height in the layout layer, so a tall
    # image never bumps the bottom — under any theme. Scoped via `:only-child`
    # so inline images are left alone.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert "p:has(> img:only-child)" in html
    assert "max-height: 66%;" in html


def test_quotation_source_standardized_to_slide_color(fixtures, tmp_path):
    # The cross-theme bridge gives `.quotation-source` the slide text colour
    # (`--fg`, `--inverse-fg` on dark slides) so it matches the quote in every
    # theme, instead of a per-theme muted/accent tint.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert ".reveal .slides section.slide .quotation-source" in html
    assert "color: var(--fg) !important;" in html
    assert "section.slide.inverse .quotation-source" in html
    assert "color: var(--inverse-fg) !important;" in html


def test_background_image_slide_is_transparent(fixtures, tmp_path):
    # A slide with a reveal background must not paint its own opaque fill over it.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert 'data-background-image="assets/grid-' in html  # bg.md sets one
    assert ".reveal .slides section.slide[data-background-image]" in html
    assert "background: transparent !important;" in html
    # reveal copies slide classes onto `.slide-background`; the bridge resets the
    # leaked padding so a cover image fills the slide with no border.
    assert ".reveal .slide-background { padding: 0 !important; }" in html


def test_visible_slides_use_flex_display_for_centering(fixtures, tmp_path):
    # reveal's default `display:block` for visible slides defeats the anchor-grid
    # vertical centering, and — applied only to the present slide — made a leaving
    # slide snap from flex-centered to block mid-transition (a text flash). We
    # pass `display: "flex"` to Reveal.initialize so reveal applies flex inline to
    # every visible slide; the centering then holds through transitions and hidden
    # slides still get display:none. (No `!important` bridge rule any more.)
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert '"display": "flex"' in html
    # the old `.present`-scoped flex bridge (the flash source) is gone; the
    # print-pdf bridge still legitimately uses `display: flex !important`.
    assert "section.slide.present" not in html


def test_print_pdf_layout_bridge_present(fixtures, tmp_path):
    # reveal's print-pdf wraps each slide in `.pdf-page`; the bridge rule keyed
    # on `.print-pdf` re-asserts the slide padding/centering so the PDF master
    # isn't jammed into the page edge. Guard the selector against regressions.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert ".print-pdf .slides .pdf-page > section.slide" in html


def test_focus_visible_styles_present(fixtures, tmp_path):
    # Visible keyboard focus for interactive content, theme-independent.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert "a:focus-visible" in html
    assert "outline: 3px solid var(--accent)" in html


def test_aria_live_announcer_present(fixtures, tmp_path):
    # A polite live region announces the current slide on navigation.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert 'id="lectern-live"' in html
    assert 'aria-live="polite"' in html
    assert ".lectern-sr-only" in html  # visually hidden
    assert "Reveal.on('slidechanged'" in html


def test_region_labelling_script_present(fixtures, tmp_path):
    # Each slide section is named (region landmark) from its heading at runtime;
    # explicit label/aria-label is preserved. Guard the script against removal.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert "Reveal.on('ready'" in html
    assert "setAttribute('aria-label'" in html


def test_lang_is_configurable(fixtures, tmp_path):
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert '<html lang="en">' in html  # default
    html_fr, _ = _render(fixtures / "render-deck", tmp_path / "fr", lang="fr")
    assert '<html lang="fr">' in html_fr


def test_mermaid_tooltip_hidden_in_print(fixtures, tmp_path):
    # Mermaid's body-appended tooltip helper would add a trailing blank PDF page;
    # hide it in print. Guard the rule against removal.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert ".mermaidTooltip { display: none !important; }" in html


def test_reduced_motion_media_query_present(fixtures, tmp_path):
    # The live deck honors prefers-reduced-motion by zeroing transition/animation.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert "transition-duration: 0s !important;" in html


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


def _mermaid_deck(tmp_path, body="```mermaid\nflowchart LR\n  A --> B\n```\n"):
    write(tmp_path, "deck.toml", 'slides = ["s.md"]\n')
    write(tmp_path, "s.md", "# Diagram\n\n" + body)
    return tmp_path


def test_mermaid_block_lowered_and_script_auto_loaded(tmp_path):
    html, _ = _render(_mermaid_deck(tmp_path / "deck"), tmp_path / "out")
    # lowered to a raw <pre class="mermaid"> — arrows intact, NOT a highlit code fence
    assert '<pre class="mermaid">' in html
    assert "A --> B" in html
    assert "language-mermaid" not in html
    # auto-detected: the mermaid module + the PDF-ready signal are present
    assert "mermaid.esm.min.mjs" in html
    assert "lecternMermaidReady" in html


def test_no_mermaid_means_no_mermaid_script(fixtures, tmp_path):
    # The .mermaid layout CSS is always present (harmless); the loader is not.
    html, _ = _render(fixtures / "render-deck", tmp_path)
    assert "mermaid.esm" not in html
    assert "lecternMermaidReady" not in html


def test_reveal_mermaid_can_be_forced_on(tmp_path):
    # `[reveal].mermaid = true` loads it even with no diagram in the deck.
    write(tmp_path, "deck.toml", 'slides = ["s.md"]\n[reveal]\nmermaid = true\n')
    write(tmp_path, "s.md", "# No diagram here\n")
    html, _ = _render(tmp_path, tmp_path / "out")
    assert "mermaid.esm.min.mjs" in html


def test_reveal_mermaid_can_be_forced_off(tmp_path):
    # `[reveal].mermaid = false` suppresses the script even with a diagram.
    src = _mermaid_deck(tmp_path / "deck")
    write(src, "deck.toml", 'slides = ["s.md"]\n[reveal]\nmermaid = false\n')
    html, _ = _render(src, tmp_path / "out")
    assert '<pre class="mermaid">' in html  # still lowered
    assert "mermaid.esm.min.mjs" not in html  # but not rendered client-side

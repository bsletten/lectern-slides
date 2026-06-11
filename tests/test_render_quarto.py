"""Quarto adapter: lowering to a `.qmd` + the `quarto render` invocation.

``quarto`` may or may not be installed; ``run_tool`` is patched so the test
exercises the generated ``deck.qmd`` and the command, not the binary.
"""

import lectern.render.quarto as quarto_mod
from lectern.config import resolve_source
from lectern.preprocess import assemble_resolved
from lectern.render import Caps, get_renderer, renderers_supporting


def _render(source, out_dir, monkeypatch, **overrides):
    calls = {}

    def fake_run(cmd, cwd, *, tool):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["tool"] = tool
        return ""

    monkeypatch.setattr(quarto_mod, "run_tool", fake_run)
    resolved = resolve_source(source, cli_overrides={"renderer": "quarto", **overrides})
    deck = assemble_resolved(resolved)
    result = get_renderer("quarto").render(deck, resolved.config, out_dir)
    qmd = (out_dir / "deck.qmd").read_text(encoding="utf-8")
    return qmd, result, calls


def test_quarto_registered_with_caps():
    adapter = get_renderer("quarto")
    assert adapter.name == "quarto"
    # HTML-only here; pdf/pptx degrade to marp.
    assert adapter.capabilities() == Caps(html=True, pdf=False, pptx=False, embeds=True)
    assert "quarto" not in renderers_supporting("pdf")
    assert "quarto" in renderers_supporting("html")


def test_available_tracks_binary(monkeypatch):
    monkeypatch.setattr(quarto_mod, "tool_available", lambda b: False)
    assert get_renderer("quarto").available() is False
    monkeypatch.setattr(quarto_mod, "tool_available", lambda b: True)
    assert get_renderer("quarto").available() is True


def test_front_matter_revealjs_format(fixtures, tmp_path, monkeypatch):
    qmd, _, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert qmd.startswith("---\n")
    assert "format:" in qmd and "revealjs:" in qmd
    assert "slide-level: 0" in qmd  # one section per Lectern slide
    assert "width: 1024" in qmd and "height: 768" in qmd  # 4:3 geometry
    assert f"css: {quarto_mod._THEME_CSS}" in qmd
    assert "html-math-method: katex" in qmd  # render-deck math = katex
    # Theme written alongside for the css: reference.
    assert (tmp_path / quarto_mod._THEME_CSS).read_text().find(".slide") != -1


def test_slides_wrapped_in_div_with_classes(fixtures, tmp_path, monkeypatch):
    qmd, _, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    # The wrapping div carries `slide` + directive classes so the theme applies.
    assert '<div class="slide center middle" id="hero">' in qmd
    assert '<div class="slide inverse"' in qmd
    # Headings become raw HTML so Quarto doesn't break a slide at each one;
    # `---` stays the sole separator.
    assert "<h1>Hero Slide</h1>" in qmd
    assert "\n# Hero Slide" not in qmd
    body = qmd.split("---\n", 2)[2]  # past the YAML front-matter
    assert "\n---\n" in body


def test_background_image_inline_style(fixtures, tmp_path, monkeypatch):
    qmd, _, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert "background-image:url(assets/grid-" in qmd


def test_notes_become_aside(fixtures, tmp_path, monkeypatch):
    qmd, _, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert '<aside class="notes">' in qmd
    assert "A speaker note for the builds slide." in qmd


def test_unsupported_attr_warns(fixtures, tmp_path, monkeypatch):
    _, result, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert any("data-x" in w for w in result.warnings)
    assert any("incremental" in w for w in result.warnings)


def test_render_invokes_quarto(fixtures, tmp_path, monkeypatch):
    _, result, calls = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert calls["tool"] == "quarto"
    assert calls["cwd"] == tmp_path
    cmd = calls["cmd"]
    assert cmd[:3] == ["quarto", "render", "deck.qmd"]
    assert "--to" in cmd and "revealjs" in cmd
    assert "--output" in cmd and "index.html" in cmd
    assert result.output == tmp_path / "index.html"


def test_passthrough_into_yaml():
    lines = quarto_mod._yaml_block(
        1280, 720, False, {"incremental": True, "logo": "x.png"}
    )
    assert "    incremental: true" in lines
    assert '    logo: "x.png"' in lines

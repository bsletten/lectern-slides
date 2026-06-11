"""Marp adapter: lowering to Marp Markdown + the subprocess invocation.

`marp-cli` is not installed in CI, so ``run_tool`` is patched to capture the
command instead of actually shelling out; the generated ``deck.marp.md`` is the
real artifact under test.
"""

import lectern.render.marp as marp_mod
from lectern.config import resolve_source
from lectern.preprocess import assemble_resolved
from lectern.render import Caps, get_renderer, renderers_supporting, supports_format


def _render(source, out_dir, monkeypatch, *, fmt="html", **overrides):
    """Render with marp, capturing the would-be subprocess command."""
    calls = {}

    def fake_run(cmd, cwd, *, tool):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["tool"] = tool
        return ""

    monkeypatch.setattr(marp_mod, "run_tool", fake_run)
    resolved = resolve_source(source, cli_overrides={"renderer": "marp", **overrides})
    deck = assemble_resolved(resolved)
    result = get_renderer("marp").render(deck, resolved.config, out_dir, fmt)
    source_md = (out_dir / "deck.marp.md").read_text(encoding="utf-8")
    return source_md, result, calls


def test_marp_registered_with_caps():
    adapter = get_renderer("marp")
    assert adapter.name == "marp"
    assert adapter.capabilities() == Caps(html=True, pdf=True, pptx=True, embeds=False)
    # Marp is the adapter that carries pdf/pptx in this build.
    assert "marp" in renderers_supporting("pdf")
    assert "marp" in renderers_supporting("pptx")


def test_available_tracks_binary(monkeypatch):
    monkeypatch.setattr(marp_mod, "tool_available", lambda b: False)
    assert get_renderer("marp").available() is False
    monkeypatch.setattr(marp_mod, "tool_available", lambda b: True)
    assert get_renderer("marp").available() is True


def test_front_matter_and_global_style(fixtures, tmp_path, monkeypatch):
    md, _, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert md.startswith("---\nmarp: true\npaginate: true\n")
    # render-deck sets math = "katex".
    assert "math: katex" in md
    # Theme injected as a global <style>, with the 4:3 slide geometry.
    assert "<style>" in md
    assert "section { width: 1024px; height: 768px; }" in md
    assert ".slide" in md  # the Lectern theme CSS is present


def test_slide_directive_lowered_to_scoped_class(fixtures, tmp_path, monkeypatch):
    md, result, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    # `.center .middle #hero data-x=1` -> scoped class (slide first); id/data dropped.
    assert "<!-- _class: slide center middle -->" in md
    assert any("id 'hero'" in w for w in result.warnings)
    assert any("data-x" in w for w in result.warnings)
    # Slides separated by horizontal rules.
    assert "\n---\n" in md.split("</style>", 1)[1]


def test_background_image_directive(fixtures, tmp_path, monkeypatch):
    md, _, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert "<!-- _class: slide inverse -->" in md
    assert '<!-- _backgroundImage: "url(assets/grid-' in md


def test_notes_become_html_comment(fixtures, tmp_path, monkeypatch):
    md, _, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert "<!--\nA speaker note for the builds slide.\n-->" in md


def test_incremental_degrades_with_warning(fixtures, tmp_path, monkeypatch):
    _, result, _ = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert any("incremental" in w for w in result.warnings)


def test_render_invokes_marp_cli_html(fixtures, tmp_path, monkeypatch):
    _, result, calls = _render(fixtures / "render-deck", tmp_path, monkeypatch)
    assert calls["tool"] == "marp-cli"
    assert calls["cwd"] == tmp_path
    cmd = calls["cmd"]
    assert cmd[:2] == ["marp", "deck.marp.md"]
    assert "-o" in cmd and "index.html" in cmd
    assert "--html" in cmd and "--allow-local-files" in cmd
    assert "--pdf" not in cmd and "--pptx" not in cmd
    assert result.output == tmp_path / "index.html"


def test_render_invokes_marp_cli_pdf_and_pptx(fixtures, tmp_path, monkeypatch):
    _, result, calls = _render(
        fixtures / "render-deck", tmp_path / "pdf", monkeypatch, fmt="pdf"
    )
    assert "--pdf" in calls["cmd"]
    assert result.output.name == "index.pdf"

    _, result2, calls2 = _render(
        fixtures / "render-deck", tmp_path / "pptx", monkeypatch, fmt="pptx"
    )
    assert "--pptx" in calls2["cmd"]
    assert result2.output.name == "index.pptx"


def test_passthrough_flags():
    assert marp_mod._passthrough({"jpeg_quality": 80, "no_stdin": True}) == [
        "--jpeg-quality",
        "80",
        "--no-stdin",
    ]
    assert marp_mod._passthrough({"off": False}) == []


def test_supports_format_helper():
    assert supports_format(Caps(html=True), "html") is True
    assert supports_format(Caps(html=True), "pdf") is False
    assert supports_format(Caps(pdf=True), "pptx") is False

"""Remark input-compat normalizer + the migration path into the reveal pipeline."""

from conftest import write

from lectern.config import resolve_source
from lectern.preprocess import assemble_resolved
from lectern.remark_compat import normalize_remark_slide


def _norm(text: str) -> str:
    return normalize_remark_slide(text)[0]


def test_property_lines_become_slide_directive():
    out = _norm("class: center, middle\nname: intro\n\n# Title")
    assert "<!-- slide: .center .middle #intro -->" in out
    assert "class: center" not in out  # property lines consumed
    assert "# Title" in out


def test_background_image_property():
    out = _norm("background-image: url(bg.png)\n\n# T")
    assert 'data-background-image="bg.png"' in out


def test_no_property_block_when_first_line_is_content():
    out = _norm("# Heading\n\nbody")
    assert "<!-- slide:" not in out
    assert "# Heading" in out


def test_unknown_key_is_not_a_property():
    # A content line that merely looks like ``key:`` must not start a block.
    out = _norm("TODO: write this slide\n\nbody")
    assert "<!-- slide:" not in out
    assert "TODO: write this slide" in out


def test_unsupported_property_warns_and_drops():
    text, warnings = normalize_remark_slide("layout: true\nclass: a\n\n# T")
    assert "<!-- slide: .a -->" in text
    assert any("layout" in w for w in warnings)


def test_inline_class_span():
    out = _norm("a .red[word] b")
    assert "[word]{.red}" in out


def test_block_class_span():
    out = _norm(".center[\n# Big\n\ntext\n]")
    assert "::: {.center}" in out
    assert ":::" in out
    assert "# Big" in out


def test_nested_class_spans():
    out = _norm("x .a[.b[deep]] y")
    assert "[[deep]{.b}]{.a}" in out


def test_unbalanced_class_span_left_alone():
    out = _norm("text .cls[oops with no close")
    assert ".cls[oops with no close" in out  # untouched, no crash


def test_increments_become_fragments():
    out = _norm("# T\n\nbase\n\n--\n\nmore")
    assert "::: {.fragment}" in out
    assert "more" in out
    assert "\n--\n" not in out  # the bare separator is gone


def test_notes_marker_becomes_notes_block():
    out = _norm("# T\n\nbody\n\n???\nspeaker note here")
    assert "<!-- notes -->" in out
    assert "<!-- /notes -->" in out
    assert "speaker note here" in out
    assert "???" not in out


# --- migration end-to-end: legacy deck -> neutral -> reveal --------------
def test_remark_compat_assemble_then_reveal(tmp_path):
    write(
        tmp_path,
        "deck.toml",
        'renderer = "reveal"\nremark_compat = true\nslides = ["s.md"]\n',
    )
    write(
        tmp_path,
        "s.md",
        "class: center\nname: hero\n\n# Migrated\n\n.accent[span] here\n\n"
        "- a\n\n--\n\n- b\n\n???\nnote\n",
    )
    resolved = resolve_source(tmp_path)
    deck = assemble_resolved(resolved)
    out = deck.markdown()
    assert "<!-- slide: .center #hero -->" in out
    assert "[span]{.accent}" in out
    assert "::: {.fragment}" in out
    assert "<!-- notes -->" in out

    # And it renders cleanly through the reveal adapter (neutral forms lowered).
    from lectern.render import get_renderer

    html = (
        get_renderer("reveal")
        .render(deck, resolved.config, tmp_path / "out")
        .output.read_text()
    )
    assert '<span class="accent">span</span>' in html
    assert 'class="fragment"' in html

"""Outline export: a linear, heading-structured Markdown transcript."""

from conftest import write

from lectern.outline import build_outline
from lectern.preprocess import assemble


def _outline(source, **overrides):
    deck = assemble(source, cli_overrides=overrides or None)
    return build_outline(deck, deck.config)


def test_title_author_header_and_body(tmp_path):
    write(
        tmp_path, "deck.toml", 'title = "My Talk"\nauthor = "Me"\nslides = ["s.md"]\n'
    )
    write(tmp_path, "s.md", "# Intro\n\nHello world.\n")
    out = _outline(tmp_path)
    assert out.startswith("# My Talk")
    assert "_Me_" in out
    assert "# Intro" in out and "Hello world." in out


def test_notes_rendered_as_blockquote(tmp_path):
    write(
        tmp_path,
        "s.md",
        "# T\n\nBody.\n\n<!-- notes -->\nSpoken words.\n<!-- /notes -->\n",
    )
    out = _outline(tmp_path / "s.md")
    assert "**Notes**" in out
    assert "> Spoken words." in out


def test_inline_span_unwrapped(tmp_path):
    write(tmp_path, "s.md", "# T\n\nA [highlight]{.accent} word.\n")
    out = _outline(tmp_path / "s.md")
    assert "A highlight word." in out
    assert "{.accent}" not in out


def test_label_synthesizes_heading(tmp_path):
    write(tmp_path, "s.md", '<!-- slide: label="Cover photo" -->\n\n![](x.jpg)\n')
    assert "## Cover photo" in _outline(tmp_path / "s.md")


def test_headingless_unlabelled_slide_is_numbered(tmp_path):
    write(tmp_path, "s.md", "Just text, no heading.\n")
    assert "## Slide 1" in _outline(tmp_path / "s.md")


def test_mermaid_collapses_to_accdescr(tmp_path):
    src = (
        "# Flow\n\n```mermaid\nflowchart LR\n  accDescr: A to B flow\n  A --> B\n```\n"
    )
    write(tmp_path, "s.md", src)
    out = _outline(tmp_path / "s.md")
    assert "A to B flow" in out  # description kept
    assert "flowchart LR" not in out  # diagram source dropped


def test_generic_comment_stripped(tmp_path):
    write(tmp_path, "s.md", "# T\n\n<!-- an author note -->\n\nVisible.\n")
    out = _outline(tmp_path / "s.md")
    assert "an author note" not in out
    assert "Visible." in out


def test_slide_directive_not_in_output(tmp_path):
    write(tmp_path, "s.md", "<!-- slide: .center -->\n\n# T\n\nBody.\n")
    out = _outline(tmp_path / "s.md")
    assert "slide:" not in out
    assert "# T" in out


def test_iframe_collapses_to_title(tmp_path):
    write(
        tmp_path,
        "s.md",
        '# Demo\n\n<iframe src="d3.html" title="Live chart"></iframe>\n',
    )
    out = _outline(tmp_path / "s.md")
    assert "> Live chart" in out
    assert "<iframe" not in out  # raw HTML dropped


def test_comment_inside_inline_code_preserved(tmp_path):
    # A `<!-- ... -->` shown as a code example is content, not a comment to strip.
    write(tmp_path, "s.md", "# T\n\nUse `<!-- slide: .center -->` at the top.\n")
    out = _outline(tmp_path / "s.md")
    assert "`<!-- slide: .center -->`" in out


def test_title_slide_heading_not_duplicated(tmp_path):
    write(tmp_path, "deck.toml", 'title = "My Talk"\nslides = ["s.md"]\n')
    write(tmp_path, "s.md", "# My Talk\n\nSubtitle line.\n")
    out = _outline(tmp_path)
    assert out.count("My Talk") == 1  # the doc title, not repeated by the slide
    assert "Subtitle line." in out

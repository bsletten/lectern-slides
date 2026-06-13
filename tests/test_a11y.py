"""Accessibility audit: source-cited warnings, and the sample deck stays clean."""

from pathlib import Path

from conftest import write

from lectern.a11y import audit
from lectern.preprocess import assemble

REPO = Path(__file__).resolve().parents[1]


def _audit(source, **overrides):
    return audit(assemble(source, cli_overrides=overrides or None))


def test_heading_slide_has_no_warning(tmp_path):
    write(tmp_path, "s.md", "# A Title\n\nSome body.\n")
    assert _audit(tmp_path / "s.md") == []


def test_label_satisfies_missing_heading(tmp_path):
    # An image-only slide is fine *with* a label (the accessible name).
    write(
        tmp_path,
        "s.md",
        '<!-- slide: label="The team in 2019" -->\n\n![](photo.jpg)\n',
    )
    assert _audit(tmp_path / "s.md") == []


def test_aria_label_also_satisfies(tmp_path):
    write(tmp_path, "s.md", '<!-- slide: aria-label="Cover" -->\n\n![](x.jpg)\n')
    assert _audit(tmp_path / "s.md") == []


def test_headingless_unlabelled_slide_warns(tmp_path):
    write(tmp_path, "s.md", "![](photo.jpg)\n")
    warns = _audit(tmp_path / "s.md")
    assert len(warns) == 1
    assert "no heading or label" in warns[0]
    assert "s.md:1" in warns[0]  # source-cited


def test_iframe_without_title_warns(tmp_path):
    write(tmp_path, "s.md", '# Demo\n\n<iframe src="d3.html"></iframe>\n')
    warns = _audit(tmp_path / "s.md")
    assert any("iframe" in w and "title=" in w for w in warns)


def test_iframe_with_title_ok_even_multiline(tmp_path):
    write(
        tmp_path,
        "s.md",
        '# Demo\n\n<iframe src="d3.html"\n  title="Live chart"></iframe>\n',
    )
    assert _audit(tmp_path / "s.md") == []


def test_heading_inside_code_fence_does_not_count(tmp_path):
    # A `#` inside a code fence is not a heading; the slide is still unnamed.
    write(tmp_path, "s.md", "```python\n# not a heading\nx = 1\n```\n")
    warns = _audit(tmp_path / "s.md")
    assert any("no heading or label" in w for w in warns)


def test_mermaid_without_acc_warns(tmp_path):
    write(tmp_path, "s.md", "# Flow\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
    warns = _audit(tmp_path / "s.md")
    assert any("mermaid" in w and "accTitle/accDescr" in w for w in warns)


def test_mermaid_with_accdescr_ok(tmp_path):
    src = (
        "# Flow\n\n```mermaid\nflowchart LR\n  accDescr: A leads to B\n  A --> B\n```\n"
    )
    write(tmp_path, "s.md", src)
    assert _audit(tmp_path / "s.md") == []


def test_mermaid_with_acctitle_ok(tmp_path):
    src = "# Flow\n\n```mermaid\nflowchart LR\n  accTitle: The flow\n  A --> B\n```\n"
    write(tmp_path, "s.md", src)
    assert _audit(tmp_path / "s.md") == []


def test_non_mermaid_fence_not_flagged_as_diagram(tmp_path):
    write(tmp_path, "s.md", "# Code\n\n```python\nA = 1\n```\n")
    assert all("mermaid" not in w for w in _audit(tmp_path / "s.md"))


def test_low_contrast_theme_warns(tmp_path):
    write(tmp_path, "theme.css", ":root { --fg: #777777; --bg: #888888; }\n")
    write(tmp_path, "s.md", "# Title\n\nbody\n")
    warns = _audit(tmp_path / "s.md", theme="theme.css")
    assert any("WCAG AA" in w and "body text" in w for w in warns)


def test_sample_deck_is_accessible():
    # Guard: the shipped sample deck must pass the audit, so slides added later
    # keep it accessible (heading/label, iframe titles, theme contrast).
    deck = assemble(REPO / "examples" / "sample-deck")
    assert audit(deck) == []

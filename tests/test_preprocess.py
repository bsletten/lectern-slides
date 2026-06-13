"""Include resolution: relative + search-path, ranges, cycles, depth, frontmatter."""

import pytest
from conftest import write

from lectern.errors import CycleError, DepthError, IncludeError, RangeError
from lectern.preprocess import assemble


def _md(deck):
    return deck.markdown(provenance=True)


def test_inline_include_resolved_relatively(tmp_path):
    write(tmp_path, "note.md", "reusable body")
    write(tmp_path, "main.md", "# Title\n\n<!-- include: note.md -->\n")
    deck = assemble(tmp_path / "main.md")
    out = _md(deck)
    assert "# Title" in out
    assert "reusable body" in out
    assert deck.slide_count == 1  # single-slide partial stays inline


def test_svg_include_collapses_blank_lines_to_stay_inline(tmp_path):
    # An inlined SVG must be one uninterrupted block: reveal's client-side
    # Markdown ends an HTML block at the first blank line, which would close
    # `<svg>` early. The include strips blank lines for .svg/.xml (but not .md).
    svg = (
        '<svg viewBox="0 0 10 10">\n'
        "  <title>t</title>\n"
        "\n"  # a blank line that would otherwise break the HTML block
        "  <rect width='10' height='10'/>\n"
        "\n"
        "</svg>\n"
    )
    write(tmp_path, "art.svg", svg)
    write(tmp_path, "main.md", "# Art\n\n<!-- include: art.svg -->\n")
    out = _md(assemble(tmp_path / "main.md"))
    block = out[out.index("<svg") : out.index("</svg>")]
    assert "<rect" in block
    assert "\n\n" not in block  # no blank line within the SVG to break the HTML block


def test_include_resolves_via_asset_base(tmp_path):
    # A themed SVG kept under asset_base (where assets live) can be inlined with
    # the same path used to reference it as an image.
    write(tmp_path, "assets/img/chart.svg", "<svg><rect/></svg>\n")
    write(tmp_path, "main.md", "<!-- include: img/chart.svg -->\n")
    deck = assemble(tmp_path / "main.md", cli_overrides={"asset_base": "assets"})
    assert "<svg><rect/></svg>" in _md(deck)


def test_md_include_keeps_blank_lines(tmp_path):
    # Markdown partials still keep blank lines — they separate paragraphs.
    write(tmp_path, "note.md", "Para one.\n\nPara two.\n")
    write(tmp_path, "main.md", "<!-- include: note.md -->\n")
    out = _md(assemble(tmp_path / "main.md"))
    assert "Para one.\n\nPara two." in out


def test_include_via_partials_search_path(tmp_path):
    write(tmp_path, "_lib/shared.md", "shared content")
    write(tmp_path, "slides/main.md", "<!-- include: shared.md -->\n")
    write(
        tmp_path,
        "deck.toml",
        'partials = ["./_lib"]\nslides = ["slides/main.md"]\n',
    )
    deck = assemble(tmp_path)
    assert "shared content" in _md(deck)


def test_relative_beats_search_path(tmp_path):
    write(tmp_path, "_lib/x.md", "from lib")
    write(tmp_path, "slides/x.md", "from sibling")
    write(tmp_path, "slides/main.md", "<!-- include: x.md -->\n")
    write(tmp_path, "deck.toml", 'partials = ["./_lib"]\nslides = ["slides/main.md"]\n')
    out = _md(assemble(tmp_path))
    assert "from sibling" in out
    assert "from lib" not in out


def test_ranged_include_selects_slides(tmp_path):
    write(tmp_path, "lib.md", "# A\n---\n# B\n---\n# C\n---\n# D")
    write(tmp_path, "main.md", "<!-- include: lib.md#1,3- -->\n")
    deck = assemble(tmp_path / "main.md")
    out = _md(deck)
    assert "# A" in out and "# C" in out and "# D" in out
    assert "# B" not in out
    assert deck.slide_count == 3


def test_provenance_comment_for_each_contributed_slide(tmp_path):
    write(tmp_path, "lib.md", "# A\n---\n# B")
    write(tmp_path, "main.md", "<!-- include: lib.md -->\n")
    out = _md(assemble(tmp_path / "main.md"))
    assert "<!-- @from lib.md slide=1 -->" in out
    assert "<!-- @from lib.md slide=2 -->" in out


def test_provenance_stripped_when_requested(tmp_path):
    write(tmp_path, "lib.md", "# A")
    write(tmp_path, "main.md", "<!-- include: lib.md -->\n")
    deck = assemble(tmp_path / "main.md")
    assert "@from" not in deck.markdown(provenance=False)


def test_nested_includes_expand(tmp_path):
    write(tmp_path, "c.md", "leaf")
    write(tmp_path, "b.md", "<!-- include: c.md -->\n")
    write(tmp_path, "a.md", "<!-- include: b.md -->\n")
    assert "leaf" in _md(assemble(tmp_path / "a.md"))


def test_missing_include_errors_with_location(tmp_path):
    write(tmp_path, "main.md", "ok\n\n<!-- include: nope.md -->\n")
    with pytest.raises(IncludeError) as ei:
        assemble(tmp_path / "main.md")
    assert ei.value.location is not None
    assert ei.value.location.line == 3  # the directive's line


def test_out_of_range_errors_cite_file(tmp_path):
    write(tmp_path, "lib.md", "# A\n---\n# B")
    write(tmp_path, "main.md", "<!-- include: lib.md#5 -->\n")
    with pytest.raises(RangeError, match=r"lib\.md"):
        assemble(tmp_path / "main.md")


def test_include_cycle_detected(tmp_path):
    write(tmp_path, "a.md", "<!-- include: b.md -->\n")
    write(tmp_path, "b.md", "<!-- include: a.md -->\n")
    with pytest.raises(CycleError):
        assemble(tmp_path / "a.md")


def test_diamond_include_is_not_a_cycle(tmp_path):
    # Same partial reached by two sibling branches is fine; only ancestors count.
    write(tmp_path, "leaf.md", "leaf body")
    write(tmp_path, "left.md", "<!-- include: leaf.md -->\n")
    write(tmp_path, "right.md", "<!-- include: leaf.md -->\n")
    write(
        tmp_path,
        "main.md",
        "<!-- include: left.md -->\n---\n<!-- include: right.md -->\n",
    )
    out = _md(assemble(tmp_path / "main.md"))
    assert out.count("leaf body") == 2


def test_depth_guard(tmp_path):
    # Chain main -> a -> b -> c; cap depth at 2 so it trips before the leaf.
    write(tmp_path, "c.md", "deep")
    write(tmp_path, "b.md", "<!-- include: c.md -->\n")
    write(tmp_path, "a.md", "<!-- include: b.md -->\n")
    write(tmp_path, "main.md", "<!-- include: a.md -->\n")
    write(tmp_path, "deck.toml", 'max_include_depth = 2\nslides = ["main.md"]\n')
    with pytest.raises(DepthError):
        assemble(tmp_path)


def test_frontmatter_in_partial_warns_and_is_dropped(tmp_path):
    write(tmp_path, "lib.md", "---\ntitle: ignore me\n---\n\nbody content")
    write(tmp_path, "main.md", "<!-- include: lib.md -->\n")
    deck = assemble(tmp_path / "main.md")
    out = _md(deck)
    assert "body content" in out
    assert "title: ignore me" not in out
    assert any("frontmatter" in w for w in deck.warnings)


def test_include_inside_fence_is_not_expanded(tmp_path):
    write(tmp_path, "secret.md", "EXPANDED")
    write(
        tmp_path,
        "main.md",
        "```\n<!-- include: secret.md -->\n```\n",
    )
    out = _md(assemble(tmp_path / "main.md"))
    assert "EXPANDED" not in out
    assert "<!-- include: secret.md -->" in out  # left as literal code


def test_directory_mode_lexical_order(tmp_path):
    write(tmp_path, "30-c.md", "third")
    write(tmp_path, "10-a.md", "first")
    write(tmp_path, "20-b.md", "second")
    deck = assemble(tmp_path)  # no deck.toml => directory mode
    out = _md(deck)
    assert out.index("first") < out.index("second") < out.index("third")
    assert deck.slide_count == 3


def test_sourcemap_maps_output_lines_to_source(tmp_path):
    write(tmp_path, "lib.md", "leaf line")
    write(tmp_path, "main.md", "top line\n\n<!-- include: lib.md -->\n")
    deck = assemble(tmp_path / "main.md")
    smap = deck.sourcemap
    lines = deck.markdown().split("\n")
    leaf_idx = next(i for i, t in enumerate(lines) if t == "leaf line")
    loc = smap.at(leaf_idx + 1)  # 1-based
    assert loc is not None
    assert loc.file == "lib.md"

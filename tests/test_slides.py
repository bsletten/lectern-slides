"""Fence-aware slide splitting."""

from lectern.slides import closes_fence, fence_marker, split_slides


def test_single_slide_when_no_separator():
    slides = split_slides("# Only\n\nbody")
    assert len(slides) == 1
    assert slides[0].text == "# Only\n\nbody"
    assert slides[0].start_line == 1


def test_splits_on_bare_triple_dash():
    slides = split_slides("a\n---\nb\n---\nc")
    assert [s.text for s in slides] == ["a", "b", "c"]
    assert [s.start_line for s in slides] == [1, 3, 5]


def test_separator_must_be_exactly_three_dashes():
    # Thematic breaks of other lengths are content, not slide breaks.
    slides = split_slides("a\n----\nb")
    assert len(slides) == 1


def test_dash_inside_backtick_fence_is_not_a_break():
    text = "intro\n\n```\n---\nstill code\n```\n\nouter"
    slides = split_slides(text)
    assert len(slides) == 1
    assert "---" in slides[0].text


def test_dash_inside_tilde_fence_is_not_a_break():
    text = "~~~\n---\n~~~\nafter"
    slides = split_slides(text)
    assert len(slides) == 1


def test_separator_after_closed_fence_still_splits():
    text = "```\ncode\n```\n---\nnext"
    slides = split_slides(text)
    assert [s.text for s in slides] == ["```\ncode\n```", "next"]


def test_start_line_offset_is_honored():
    # Simulates content that began on line 4 after a 3-line frontmatter block.
    slides = split_slides("a\n---\nb", start_line=4)
    assert [s.start_line for s in slides] == [4, 6]


def test_fence_marker_detection():
    assert fence_marker("```python").length == 3
    assert fence_marker("~~~~").char == "~"
    assert fence_marker("   ```").length == 3  # up to 3 leading spaces
    assert fence_marker("    ```") is None  # 4 spaces => indented code, not a fence
    assert fence_marker("text") is None


def test_closes_fence_requires_no_info_and_matching_run():
    opener = fence_marker("```python")
    assert closes_fence("```", opener)
    assert closes_fence("````", opener)  # longer run closes
    assert not closes_fence("``", opener)  # shorter run does not
    assert not closes_fence("```ruby", opener)  # closing fence carries no info
    assert not closes_fence("~~~", opener)  # different char

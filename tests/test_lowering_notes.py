"""Lowering: the two notes buckets (handout vs. presenter-only)."""

from pathlib import Path

from lectern.assets import AssetResolver
from lectern.render.lowering import scan_slide
from lectern.sourcemap import OutLine, SourceLocation


def _scan(text: str, tmp_path: Path):
    group = [
        OutLine(line, SourceLocation("deck.md", i + 1))
        for i, line in enumerate(text.splitlines())
    ]
    resolver = AssetResolver(tmp_path, None, tmp_path, [])
    return scan_slide(group, resolver, tmp_path)


def test_comment_form_splits_handout_and_presenter_notes(tmp_path):
    slide = _scan(
        "# Slide\n"
        "<!-- notes -->\n"
        "handout note\n"
        "<!-- /notes -->\n"
        "<!-- notes:presenter -->\n"
        "stage-only note\n"
        "<!-- /notes -->\n",
        tmp_path,
    )
    assert slide.notes == ["handout note"]
    assert slide.presenter_notes == ["stage-only note"]
    # the speaker view sees both, handout notes first
    assert slide.speaker_notes == ["handout note", "stage-only note"]


def test_div_form_presenter_notes(tmp_path):
    slide = _scan(
        "# Slide\n::: {.notes .presenter}\nstage-only note\n:::\n",
        tmp_path,
    )
    assert slide.notes == []
    assert slide.presenter_notes == ["stage-only note"]
    # class order doesn't matter
    other = _scan("# S\n::: {.presenter .notes}\nx\n:::\n", tmp_path)
    assert other.presenter_notes == ["x"]


def test_unknown_category_warns_and_falls_back_to_handout(tmp_path):
    slide = _scan(
        "# Slide\n<!-- notes:presetner -->\noops\n<!-- /notes -->\n",
        tmp_path,
    )
    # a typo'd category is treated as an ordinary handout note, but flagged
    assert slide.notes == ["oops"]
    assert slide.presenter_notes == []
    assert any("unknown notes category 'presetner'" in w for w in slide.warnings)

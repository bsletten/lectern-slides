"""Golden-file assembly: the fixture deck must assemble byte-for-byte stably.

Provenance paths are relative to the deck root, so the golden is independent of
where the repo lives on disk. Regenerate intentionally with::

    lectern assemble tests/fixtures/deck > tests/fixtures/deck.assembled.golden.md
"""

from lectern.preprocess import assemble


def test_fixture_deck_matches_golden(fixtures):
    golden = (fixtures / "deck.assembled.golden.md").read_text(encoding="utf-8")
    deck = assemble(fixtures / "deck")
    assert deck.markdown(provenance=True) == golden
    assert deck.warnings == []

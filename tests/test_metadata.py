"""Deck metadata → JSON-LD (pure functions)."""

import json

from lectern.config import Config
from lectern.metadata import build_jsonld, merge_tags, render_script


def _cfg(**over) -> Config:
    return Config.model_validate(over)


def test_merge_tags_order_preserving_dedupe():
    assert merge_tags(["a", "b"], ["b", " c ", "a"]) == ["a", "b", "c"]
    assert merge_tags([], []) == []


def test_build_jsonld_matches_the_context_contract():
    cfg = _cfg(
        title="Full Stack Engineering - Encryption",
        metadata={"link": "https://x/fs-crypto/", "tags": ["identity"]},
    )
    doc = build_jsonld(cfg, ["post-quantum", "uberconf", "nfjs"])
    assert doc["@type"] == "cms:Presentation"
    assert doc["@context"]["dc"] == "http://purl.org/dc/elements/1.1/"
    assert doc["@context"]["cms"] == "https://ikigai-rs.dev/ns/cms#"
    assert doc["@context"]["tags"] == {"@id": "dc:subject", "@container": "@set"}
    assert doc["@context"]["link"] == "dc:identifier"
    assert doc["title"] == "Full Stack Engineering - Encryption"
    assert doc["tags"] == ["identity", "post-quantum", "uberconf", "nfjs"]
    assert doc["link"] == "https://x/fs-crypto/"


def test_metadata_title_overrides_deck_title_but_falls_back_to_it():
    assert build_jsonld(_cfg(title="Deck"))["title"] == "Deck"
    override = build_jsonld(_cfg(title="Deck", metadata={"title": "Meta"}))
    assert override["title"] == "Meta"


def test_context_section_extends_the_base_context():
    cfg = _cfg(
        title="T", metadata={"context": {"ex": "https://ex/", "cms": "urn:cms#"}}
    )
    ctx = build_jsonld(cfg)["@context"]
    assert ctx["ex"] == "https://ex/"  # added
    assert ctx["cms"] == "urn:cms#"  # overridden
    assert ctx["dc"] == "http://purl.org/dc/elements/1.1/"  # base retained


def test_empty_metadata_emits_nothing():
    assert build_jsonld(_cfg()) is None
    assert render_script(_cfg()) == ""


def test_render_script_is_valid_json_and_escapes_script_close():
    # A tag containing `</script>` must not end the element; `<` is escaped to a
    # JSON unicode escape, which is inert to the HTML parser but still valid JSON.
    script = render_script(_cfg(title="T", metadata={"tags": ["</script>"]}))
    assert script.startswith('<script type="application/ld+json">')
    assert "</script>" not in script[: -len("</script>")]  # only the real closer
    payload = script[script.index("{") : script.rindex("}") + 1]
    assert json.loads(payload)["tags"] == ["</script>"]


def test_non_ascii_tags_stay_readable():
    script = render_script(_cfg(title="T", metadata={"tags": ["暗号"]}))
    assert "暗号" in script

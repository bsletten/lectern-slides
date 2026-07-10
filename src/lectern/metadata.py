"""Deck metadata → JSON-LD.

The ``[metadata]`` config section plus deck-global ``<!-- tags: a, b -->``
markdown directives (collected in :mod:`lectern.preprocess`) render as a single
``<script type="application/ld+json">`` in the deck ``<head>``. The ``@context``
maps the friendly terms onto Dublin Core and the ikigai CMS vocabulary; a deck
may extend it via ``[metadata.context]``.

Pure functions, no I/O — the heavy-tested seam.
"""

from __future__ import annotations

import json

# The fixed base context. ``[metadata.context]`` merges on top of this, so a deck
# can add prefixes/terms (or override one) without restating the defaults.
_BASE_CONTEXT: dict = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "cms": "https://ikigai-rs.dev/ns/cms#",
    "title": "dc:title",
    "tags": {"@id": "dc:subject", "@container": "@set"},
    "link": "dc:identifier",
}


def merge_tags(*groups: list[str]) -> list[str]:
    """Order-preserving union of tag lists (config tags first, then directives)."""
    seen: dict[str, None] = {}
    for group in groups:
        for tag in group:
            t = tag.strip()
            if t:
                seen.setdefault(t, None)
    return list(seen)


def build_jsonld(config, deck_tags: list[str] | None = None) -> dict | None:
    """Build the JSON-LD document for a deck, or ``None`` if there's nothing to say.

    Merges ``[metadata].tags`` with ``deck_tags`` (from markdown directives) and
    falls back to the top-level deck ``title`` when ``[metadata].title`` is unset.
    Returns ``None`` when no title, tags, or link are present, so a metadata-less
    deck emits no ``<script>``.
    """
    md = config.metadata
    title = md.title or config.title
    tags = merge_tags(md.tags, deck_tags or [])
    link = md.link

    if not (title or tags or link):
        return None

    context = {**_BASE_CONTEXT, **(md.context or {})}
    doc: dict = {"@context": context, "@type": md.type}
    if title:
        doc["title"] = title
    if tags:
        doc["tags"] = tags
    if link:
        doc["link"] = link
    return doc


def render_script(config, deck_tags: list[str] | None = None) -> str:
    """Render the ``<script type="application/ld+json">`` block, or ``""``.

    The payload is JSON, and JSON has no way to write a literal ``</script>`` that
    the HTML parser wouldn't end the element on, so we escape the ``<`` — valid
    JSON (``\\u003c``), inert to the parser. ``ensure_ascii=False`` keeps CJK and
    other non-ASCII tag text readable in the source.
    """
    doc = build_jsonld(config, deck_tags)
    if doc is None:
        return ""
    payload = json.dumps(doc, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    return f'<script type="application/ld+json">\n{payload}\n</script>'

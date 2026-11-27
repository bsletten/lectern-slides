"""Where a reveal deck loads reveal.js from: ``[reveal] assets``.

* ``"cdn"`` (default) — reveal.js 5.1.0 from jsDelivr, byte-identical to every
  earlier build.
* ``"vendored"`` — the copy of reveal.js 5.1.0 shipped inside this package
  (``lectern/vendor/reveal.js``, MIT, see its ``NOTICE.md``).
* ``"local"`` — a directory the deck names with ``[reveal] path``, resolved
  against the deck root like every deck path and read through the deck's
  :class:`~lectern.source.Source`.

In the two self-contained modes each file is copied into ``assets/`` under a
content-hashed name, so the built page loads only relative paths. Mermaid, the
math plugin (KaTeX/MathJax) and the free Font Awesome kit are still CDN-only, so
a self-contained deck that needs them is refused with a sentence rather than
silently reaching out to the network.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

from ..errors import ConfigError

REVEAL_VERSION = "5.1.0"
REVEAL_CDN = f"https://cdn.jsdelivr.net/npm/reveal.js@{REVEAL_VERSION}"

MODES = ("cdn", "vendored", "local")

# Template slot → path inside a reveal.js package (the npm tarball's layout).
_CORE = {
    "reset": "dist/reset.css",
    "css": "dist/reveal.css",
    "js": "dist/reveal.js",
    "markdown": "plugin/markdown/markdown.js",
    "notes": "plugin/notes/notes.js",
}
_HIGHLIGHT = {"highlight": "plugin/highlight/highlight.js"}
_MATH = {"math": "plugin/math/math.js"}


def mode_of(config) -> str:
    mode = config.reveal.model_dump().get("assets") or "cdn"
    if mode not in MODES:
        raise ConfigError(
            f'[reveal] assets = "{mode}" is not a mode lectern knows; '
            'use "cdn", "vendored" or "local"'
        )
    return mode


def required_files(*, highlight: bool, math: bool) -> dict[str, str]:
    files = dict(_CORE)
    if highlight:
        files.update(_HIGHLIGHT)
    if math:
        files.update(_MATH)
    return files


def refuse_cdn_only(
    config, *, mermaid: bool, math: bool, font_awesome: bool | str
) -> None:
    """Refuse a self-contained deck that uses a feature lectern only loads remotely."""
    mode = mode_of(config)
    if mode == "cdn":
        return
    where = f'[reveal] assets = "{mode}"'
    if math:
        raise ConfigError(
            f"{where} cannot render math: reveal's math plugin loads KaTeX or "
            "MathJax from a CDN, and lectern does not vendor them yet; set "
            '[reveal] assets = "cdn" or remove [reveal] math'
        )
    if mermaid:
        raise ConfigError(
            f"{where} cannot render Mermaid diagrams: lectern loads Mermaid from "
            'a CDN and does not vendor it yet; set [reveal] assets = "cdn" or '
            "remove the ```mermaid blocks (and [reveal] mermaid)"
        )
    if font_awesome is True:
        raise ConfigError(
            f"{where} cannot use font_awesome = true, the free kit from a CDN; "
            "point font_awesome at a local kit directory instead"
        )


def resolve(config, root: Path, source, resolver, *, highlight: bool, math: bool):
    """Return ``{slot: href}`` for the template, copying files in local modes."""
    mode = mode_of(config)
    files = required_files(highlight=highlight, math=math)
    if mode == "cdn":
        return {slot: f"{REVEAL_CDN}/{rel}" for slot, rel in files.items()}

    if mode == "vendored":
        base = resources.files("lectern") / "vendor" / "reveal.js"
        return {
            slot: resolver.copy_bytes(Path(rel).name, (base / rel).read_bytes())
            for slot, rel in files.items()
        }

    raw = config.reveal.model_dump().get("path")
    if not raw:
        raise ConfigError(
            '[reveal] assets = "local" needs [reveal] path, the directory '
            "holding reveal.js's dist/ and plugin/ files"
        )
    p = Path(str(raw)).expanduser()
    directory = p if p.is_absolute() else root / p
    missing = [rel for rel in files.values() if not source.exists(directory / rel)]
    if len(missing) == len(files):
        raise ConfigError(
            f'[reveal] path "{raw}" holds no reveal.js files (looked in '
            f"{directory} for {', '.join(files.values())})"
        )
    if missing:
        raise ConfigError(
            f'[reveal] path "{raw}" is missing {", ".join(missing)}, which this '
            "deck needs from reveal.js"
        )
    return {
        slot: resolver.copy_bytes(Path(rel).name, source.read_bytes(directory / rel))
        for slot, rel in files.items()
    }


# --------------------------------------------------------------------------- #
# remote-load scan
# --------------------------------------------------------------------------- #
_REMOTE = r"((?:https?:)?//[^\s\"'<>)]+)"
_REMOTE_LOADS = (
    # <script src>, <link href>, <img src>, <iframe src>, media, <object data>, …
    re.compile(
        r"<(?:script|link|img|iframe|video|audio|source|track|embed|object|input)"
        r"\b[^>]*?\s(?:src|href|data|poster|srcset)\s*=\s*[\"']?" + _REMOTE,
        re.IGNORECASE,
    ),
    # ES module imports: `import x from '…'`, `import '…'`, `import('…')`
    re.compile(r"\bimport\b[^;'\"]*?\(?\s*[\"']" + _REMOTE),
    # CSS url(…) and @import
    re.compile(r"url\(\s*[\"']?" + _REMOTE, re.IGNORECASE),
    re.compile(r"@import\s+[\"']" + _REMOTE, re.IGNORECASE),
    # Markdown images, rendered client-side by reveal's markdown plugin
    re.compile(r"!\[[^\]]*\]\(\s*<?" + _REMOTE),
)


def remote_loads(html_text: str) -> list[str]:
    """Every URL on another host that *html_text* would load, in order, once."""
    hits: list[tuple[int, str]] = []
    for pattern in _REMOTE_LOADS:
        hits.extend((m.start(1), m.group(1)) for m in pattern.finditer(html_text))
    return list(dict.fromkeys(url for _, url in sorted(hits)))

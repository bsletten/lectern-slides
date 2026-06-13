"""Asset resolution: rewrite references and copy local files into the output.

A reference is any image target, ``src``, ``href``, ``poster``, or
``data-background-image/-video``. Resolution (spec §6, with one author-friendly
addition):

* ``http(s)://…``, protocol-relative ``//…``, ``data:``, ``mailto:``, ``#anchor``
  → left untouched;
* **root-absolute** ``/p`` → joined with ``asset_base`` (a URL is prefixed; a
  local dir is read from ``asset_base/p``);
* **relative** ``p`` → resolved against the *including file's* directory, then —
  if a local ``asset_base`` dir is configured — against that (this is what lets a
  deck keep ``bg.svg`` in ``assets/`` while referencing it bare from a slide);
  a relative ref under a URL ``asset_base`` that isn't found locally is prefixed;
* local hits are copied into ``<out_dir>/assets/`` (de-duplicated by content
  hash) and the reference rewritten to a relative ``assets/…`` path;
* a missing asset is a warning (the build continues), citing the slide.

Rewriting is applied per content line by the adapter, so it never touches
references that appear inside fenced code blocks.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

# ![alt](REF  — capture the prefix and the ref; title/closing paren are untouched.
_MD_IMAGE = re.compile(r"(!\[[^\]]*\]\()\s*<?([^)\s>]+)")
# HTML attribute references (quoted).
_HTML_ATTR = re.compile(
    r"\b(src|href|poster|data-background-image|data-background-video)"
    r'\s*=\s*(["\'])(.*?)\2',
    re.IGNORECASE,
)

_PASSTHROUGH_PREFIXES = (
    "http://",
    "https://",
    "//",
    "data:",
    "mailto:",
    "tel:",
    "#",
    "javascript:",
)


class AssetResolver:
    """Resolves and copies a deck's assets into ``out_dir/assets``."""

    def __init__(
        self,
        root: Path,
        asset_base: str | None,
        out_dir: Path,
        warnings: list[str],
    ):
        self.root = root
        self.out_dir = out_dir
        self.assets_dir = out_dir / "assets"
        self.warnings = warnings
        self.copied: list[Path] = []
        self.missing: list[str] = []
        self._by_hash: dict[str, str] = {}

        self.asset_base_url: str | None = None
        self.asset_base_dir: Path | None = None
        if asset_base:
            if asset_base.lower().startswith(("http://", "https://", "//")):
                self.asset_base_url = asset_base
            else:
                p = Path(asset_base).expanduser()
                self.asset_base_dir = p if p.is_absolute() else (root / p)

    def rewrite(self, text: str, base_dir: Path, source_label: str) -> str:
        """Rewrite every asset reference found in *text*."""

        def image_sub(m: re.Match) -> str:
            return m.group(1) + self.resolve(m.group(2), base_dir, source_label)

        def attr_sub(m: re.Match) -> str:
            new = self.resolve(m.group(3), base_dir, source_label)
            return f"{m.group(1)}={m.group(2)}{new}{m.group(2)}"

        text = _MD_IMAGE.sub(image_sub, text)
        return _HTML_ATTR.sub(attr_sub, text)

    def resolve(self, ref: str, base_dir: Path, source_label: str) -> str:
        """Resolve a single reference, copying a local hit. Returns the new ref."""
        raw = ref.strip()
        if not raw or raw.lower().startswith(_PASSTHROUGH_PREFIXES):
            return ref

        if raw.startswith("/"):
            if self.asset_base_url:
                return _join_url(self.asset_base_url, raw)
            base = self.asset_base_dir or self.root
            candidates = [base / raw.lstrip("/")]
        else:
            p = Path(raw).expanduser()
            if p.is_absolute():
                candidates = [p]
            else:
                candidates = [base_dir / p]
                if self.asset_base_dir is not None:
                    candidates.append(self.asset_base_dir / p)

        for candidate in candidates:
            if candidate.is_file():
                return self._copy(candidate)

        if self.asset_base_url and not raw.startswith("/"):
            return _join_url(self.asset_base_url, raw)

        self.warnings.append(f"{source_label}: asset not found: {ref}")
        self.missing.append(ref)
        return ref

    def _copy(self, src: Path) -> str:
        data = src.read_bytes()
        digest = hashlib.sha256(data).hexdigest()[:8]
        if digest in self._by_hash:
            return self._by_hash[digest]

        name = f"{src.stem}-{digest}{src.suffix}"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        dest = self.assets_dir / name
        if not dest.exists():
            dest.write_bytes(data)
        rel = f"assets/{name}"
        self._by_hash[digest] = rel
        self.copied.append(dest)
        return rel

    def prune_stale(self) -> list[Path]:
        """Delete files in ``assets/`` that this build did not (re)write.

        Assets are content-hash named and never overwritten in place, so an edited
        or removed asset leaves its old hash behind; across rebuilds ``assets/``
        accumulates orphans. Remove any flat file there not produced this run, so
        a plain ``build`` yields the same ``assets/`` a clean rebuild would.

        Only ever touches the deck's own ``out_dir/assets``; subdirectories (a
        copied ``font-awesome`` kit lives in ``out_dir/font-awesome``, elsewhere)
        are left untouched. Returns the files removed.
        """
        if not self.assets_dir.is_dir():
            return []
        kept = {p.resolve() for p in self.copied}
        removed: list[Path] = []
        for child in sorted(self.assets_dir.iterdir()):
            if child.is_file() and child.resolve() not in kept:
                child.unlink()
                removed.append(child)
        return removed


def _join_url(base: str, ref: str) -> str:
    return f"{base.rstrip('/')}/{ref.lstrip('/')}"

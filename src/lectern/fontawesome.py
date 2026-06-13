"""Font Awesome support for the native HTML adapters.

The ``font_awesome`` config value drives a single ``<head>`` stylesheet:

* ``false`` / unset → off;
* ``true`` → the **free** kit from a pinned CDN (set it in a deck's ``deck.toml``
  for a shareable deck);
* a **path** → a locally checked-in kit (e.g. a Pro kit, set once in your user
  config so every deck inherits it) — **self-hosted by copying the directory
  verbatim** into ``<out_dir>/font-awesome``. The verbatim copy matters: Font
  Awesome's ``all.min.css`` references its fonts with relative ``../webfonts/``
  URLs, which the per-file, content-hashing asset pipeline would break.

Icons themselves (``<i class="fa-solid fa-house"></i>``) are raw HTML that the
lowering layer already passes through untouched; this module only loads the CSS.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Pinned free major — bump deliberately (a silent 6→7 jump can move/rename icons).
FREE_CDN = (
    "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.7.2/css/all.min.css"
)


def resolve(
    font_awesome: bool | str, root: Path, out_dir: Path, warnings: list[str]
) -> str | None:
    """Return the ``<head>`` stylesheet href for Font Awesome, or ``None`` if off.

    For a local kit, copies the directory verbatim into ``out_dir/font-awesome``
    (preserving its ``css/`` + ``webfonts/`` layout) and returns a relative href.
    """
    if not font_awesome:
        return None
    if font_awesome is True:
        return FREE_CDN

    # A path to a local kit to self-host (relative resolves against the deck root).
    src = Path(font_awesome).expanduser()
    src = src if src.is_absolute() else (root / src)
    if not src.is_dir():
        warnings.append(f"font_awesome: directory not found: {src}")
        return None

    css = _find_css(src)
    if css is None:
        warnings.append(f"font_awesome: no css/all(.min).css under {src}")
        return None

    dest = out_dir / "font-awesome"
    # dirs_exist_ok so re-builds overwrite in place (no rmtree of an output dir).
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return f"font-awesome/{css.relative_to(src).as_posix()}"


def _find_css(src: Path) -> Path | None:
    """The kit's main stylesheet — the standard locations, then any ``all*.css``."""
    for name in ("css/all.min.css", "css/all.css"):
        if (src / name).is_file():
            return src / name
    hits = sorted(src.glob("**/all*.css"))
    return hits[0] if hits else None

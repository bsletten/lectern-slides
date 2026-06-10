"""Theme resolution and design-token injection.

A theme is a CSS file driven by design tokens (CSS custom properties). The
``theme`` config value is either a **bundled name** (``"base"`` → the packaged
``themes/base.css``) or a **path** (``"./themes/mine.css"``, ``"~/house.css"``,
or absolute) — and like every deck path, a relative theme path resolves against
the deck root, never the CWD.

The deck's ``aspect`` drives the slide geometry: we compute ``(width, height)``
and append a ``:root`` override for ``--slide-w`` / ``--slide-h`` *after* the
theme so the deck's configured aspect always wins over a theme's baked-in
default. The same dimensions feed the reveal adapter's ``width``/``height``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .errors import ConfigError

# Named aspect ratios with their canonical authoring pixel dimensions.
_ASPECT_DIMENSIONS = {
    "16:9": (1280, 720),
    "16:10": (1280, 800),
    "4:3": (1024, 768),
}


@dataclass(frozen=True)
class Theme:
    """A resolved theme: its CSS (with token overrides) and slide geometry."""

    name: str
    css: str
    width: int
    height: int


def slide_dimensions(aspect: str) -> tuple[int, int]:
    """Map an ``aspect`` string to ``(width, height)`` in pixels.

    Accepts named ratios (``"16:9"``), arbitrary ratios (``"3:2"`` → height 720),
    and explicit pixel sizes (``"1280x720"``).
    """
    a = aspect.strip().lower()
    if a in _ASPECT_DIMENSIONS:
        return _ASPECT_DIMENSIONS[a]

    pixels = re.fullmatch(r"(\d+)\s*x\s*(\d+)", a)
    if pixels:
        return int(pixels.group(1)), int(pixels.group(2))

    ratio = re.fullmatch(r"(\d+)\s*:\s*(\d+)", a)
    if ratio:
        rw, rh = int(ratio.group(1)), int(ratio.group(2))
        if rw == 0 or rh == 0:
            raise ConfigError(f"invalid aspect '{aspect}'")
        height = 720
        return round(height * rw / rh), height

    raise ConfigError(
        f"invalid aspect '{aspect}' (use '16:9', a 'W:H' ratio, or '1280x720')"
    )


def _is_path_like(theme: str) -> bool:
    return (
        theme.endswith(".css")
        or "/" in theme
        or theme.startswith((".", "~"))
        or Path(theme).is_absolute()
    )


def resolve_theme_css(theme: str, root: Path) -> tuple[str, str]:
    """Return ``(name, css)`` for a bundled theme name or a deck-relative path."""
    if _is_path_like(theme):
        p = Path(theme).expanduser()
        if not p.is_absolute():
            p = root / p
        if not p.is_file():
            raise ConfigError(f"theme file not found: {p}")
        return p.stem, p.read_text(encoding="utf-8")

    resource = files("lectern").joinpath("themes", f"{theme}.css")
    if not resource.is_file():
        raise ConfigError(
            f"unknown bundled theme '{theme}' (expected a bundled name like "
            "'base', or a path ending in .css)"
        )
    return theme, resource.read_text(encoding="utf-8")


def build_theme(theme: str, aspect: str, root: Path) -> Theme:
    """Resolve the theme and inject the aspect-driven geometry tokens."""
    name, css = resolve_theme_css(theme, root)
    width, height = slide_dimensions(aspect)
    override = (
        "\n/* lectern: aspect override */\n"
        f":root {{ --slide-w: {width}px; --slide-h: {height}px; }}\n"
    )
    return Theme(name=name, css=css + override, width=width, height=height)

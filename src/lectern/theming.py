"""Theme resolution and design-token injection.

A theme is a CSS file driven by design tokens (CSS custom properties). The
``theme`` config value is either a **path** (``"./themes/mine.css"``,
``"~/house.css"``, or absolute — a relative path resolves against the deck root)
or a **bare name** (``"base"``), which is searched in the configured
``theme_paths`` directories first and then in the package's bundled themes. That
lets a deck or user config keep a reusable theme library outside the package and
still refer to themes by name.

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


def is_theme_path(theme: str) -> bool:
    """Whether ``theme`` is a path (vs a bundled theme name like ``base``)."""
    return (
        theme.endswith(".css")
        or "/" in theme
        or theme.startswith((".", "~"))
        or Path(theme).is_absolute()
    )


def resolve_theme_dirs(theme_paths: list[str], root: Path) -> list[Path]:
    """Resolve ``theme_paths`` entries to absolute dirs (relative → deck root)."""
    dirs: list[Path] = []
    for entry in theme_paths:
        p = Path(entry).expanduser()
        dirs.append(p if p.is_absolute() else (root / p))
    return dirs


def resolve_theme_css(
    theme: str, root: Path, theme_dirs: list[Path] | tuple[Path, ...] = ()
) -> tuple[str, str]:
    """Return ``(name, css)`` for a theme name or a deck-relative path.

    A **path** (``./x.css``, ``~/x.css``, absolute) is loaded directly. A bare
    **name** is searched first in ``theme_dirs`` (the configured ``theme_paths``,
    in order), then in the package's bundled themes — so a deck or user config can
    keep a reusable theme library outside the package and still use it by name.
    """
    if is_theme_path(theme):
        p = Path(theme).expanduser()
        if not p.is_absolute():
            p = root / p
        if not p.is_file():
            raise ConfigError(f"theme file not found: {p}")
        return p.stem, p.read_text(encoding="utf-8")

    for directory in theme_dirs:
        candidate = directory / f"{theme}.css"
        if candidate.is_file():
            return theme, candidate.read_text(encoding="utf-8")

    resource = files("lectern").joinpath("themes", f"{theme}.css")
    if resource.is_file():
        return theme, resource.read_text(encoding="utf-8")

    searched = ", ".join(str(d) for d in theme_dirs) or "(none configured)"
    raise ConfigError(
        f"unknown theme '{theme}': not a .css path, not found in theme_paths "
        f"[{searched}], and not a bundled theme"
    )


def bundled_theme_names() -> list[str]:
    """Sorted names of the themes packaged with lectern."""
    themes = files("lectern").joinpath("themes")
    return sorted(r.name[:-4] for r in themes.iterdir() if r.name.endswith(".css"))


def available_themes(
    theme_dirs: list[Path] | tuple[Path, ...],
) -> list[tuple[str, str]]:
    """``(name, source)`` for every theme usable by name, sorted by name.

    Mirrors :func:`resolve_theme_css`'s search order: the configured
    ``theme_paths`` (each dir, in order) shadow the bundled set, so the first
    occurrence of a name wins and its ``source`` is that file's path; a bundled
    theme's source is the string ``"bundled"``.
    """
    seen: dict[str, str] = {}
    for directory in theme_dirs:
        if directory.is_dir():
            for css in sorted(directory.glob("*.css")):
                seen.setdefault(css.stem, str(css))
    for name in bundled_theme_names():
        seen.setdefault(name, "bundled")
    return sorted(seen.items())


def build_theme(
    theme: str, aspect: str, root: Path, theme_paths: list[str] | None = None
) -> Theme:
    """Resolve the theme and inject the aspect-driven geometry tokens."""
    theme_dirs = resolve_theme_dirs(theme_paths or [], root)
    name, css = resolve_theme_css(theme, root, theme_dirs)
    width, height = slide_dimensions(aspect)
    override = (
        "\n/* lectern: aspect override */\n"
        f":root {{ --slide-w: {width}px; --slide-h: {height}px; }}\n"
    )
    return Theme(name=name, css=css + override, width=width, height=height)

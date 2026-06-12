"""Theme color tokens → perceptual-luminance grays (the ``tokens`` B&W engine).

We read the theme's ``:root`` custom properties, keep only the ones that hold a
color, and map each to the gray of equal *perceptual luminance* (sRGB-linearized
Rec.709). Two different hues of similar lightness stay distinguishable instead of
collapsing to mud, and — because it's a token swap, not a raster filter — the
output stays vector and text-crisp. Raster images / captured posters are not
touched here (use the ``ghostscript`` engine for those).

Pure functions only: no I/O. The print-CSS builder injects the resulting
``:root`` override after the theme so the grays win.
"""

from __future__ import annotations

import re

_TOKEN_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_root_tokens(css: str) -> dict[str, str]:
    """Extract every ``--name: value`` declaration from the theme CSS.

    Not a real CSS parser — themes declare tokens as simple ``--k: v;`` lines, and
    that's all we need. Later declarations win (matching the cascade).
    """
    tokens: dict[str, str] = {}
    for name, value in _TOKEN_DECL.findall(css):
        tokens[name] = value.strip()
    return tokens


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    m = _HEX.match(value.strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c: float) -> int:
    s = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return max(0, min(255, round(s * 255)))


def luminance(rgb: tuple[int, int, int]) -> float:
    """Relative luminance in [0, 1] (sRGB-linearized Rec.709 weights)."""
    r, g, b = (_to_linear(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def to_gray(value: str) -> str | None:
    """Map a hex color to the equal-luminance gray hex, or ``None`` if not hex."""
    rgb = _hex_to_rgb(value)
    if rgb is None:
        return None
    g = _to_srgb(luminance(rgb))
    return f"#{g:02x}{g:02x}{g:02x}"


def contrast(a: str, b: str) -> float | None:
    """WCAG 2.x contrast ratio between two hex colors (≥1), or ``None`` if either
    value isn't a plain hex color (e.g. ``color-mix(...)`` — left to the browser)."""
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    if ra is None or rb is None:
        return None
    la, lb = luminance(ra), luminance(rb)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def gray_token_overrides(css: str) -> dict[str, str]:
    """For each color-valued token in the theme, its equal-luminance gray hex."""
    grays: dict[str, str] = {}
    for name, value in parse_root_tokens(css).items():
        gray = to_gray(value)
        if gray is not None:
            grays[name] = gray
    return grays

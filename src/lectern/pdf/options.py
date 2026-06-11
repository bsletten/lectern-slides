"""Resolved PDF options: ``[pdf]`` config + the ``ink_saver`` preset.

CLI flags are merged into :class:`~lectern.config.PdfConfig` upstream (in the
build command), so by the time we get here the only derivation left is expanding
the ``ink_saver`` convenience preset, which the spec defines as
``bw`` + ``backgrounds = false`` + ``light_inverse = true``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..errors import ConfigError

if TYPE_CHECKING:
    from ..config import PdfConfig

LAYOUTS = ("1up", "2up", "2up-notes", "4up", "2x2", "6up", "3up-notes")
COLORS = ("color", "bw")
BW_ENGINES = ("tokens", "ghostscript")
FRAGMENTS = ("flatten", "steps")
POSTERS = ("auto", "explicit", "off")
ORIENTATIONS = ("portrait", "landscape")


@dataclass(frozen=True)
class PdfOptions:
    """The fully-resolved PDF export settings for one build."""

    # render-time
    backgrounds: bool
    light_inverse: bool
    fragments: str
    paper: str
    posters: str
    poster_at: int
    # color
    color: str
    bw_engine: str
    # imposition
    layout: str
    orientation: str
    margins: str
    gutter: str
    frame: bool
    slide_numbers: bool
    header: str
    footer: str

    @property
    def bw(self) -> bool:
        return self.color == "bw"


def _check(value: str, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise ConfigError(
            f"invalid [pdf] {field} '{value}' (expected one of: {', '.join(allowed)})"
        )
    return value


def resolve(pdf: PdfConfig) -> PdfOptions:
    """Resolve a :class:`PdfConfig` into the immutable :class:`PdfOptions`."""
    backgrounds = pdf.backgrounds
    light_inverse = pdf.light_inverse
    color = _check(pdf.color, COLORS, "color")

    # ink_saver is a one-flag handout preset; it overrides the three knobs.
    if pdf.ink_saver:
        color = "bw"
        backgrounds = False
        light_inverse = True

    layout = "2x2" if pdf.layout == "4up" else pdf.layout
    _check(layout, LAYOUTS, "layout")

    return PdfOptions(
        backgrounds=backgrounds,
        light_inverse=light_inverse,
        fragments=_check(pdf.fragments, FRAGMENTS, "fragments"),
        paper=pdf.paper,
        posters=_check(pdf.posters, POSTERS, "posters"),
        poster_at=pdf.poster_at,
        color=color,
        bw_engine=_check(pdf.bw_engine, BW_ENGINES, "bw_engine"),
        layout=layout,
        orientation=_check(pdf.orientation, ORIENTATIONS, "orientation"),
        margins=pdf.margins,
        gutter=pdf.gutter,
        frame=pdf.frame,
        slide_numbers=pdf.slide_numbers,
        header=pdf.header,
        footer=pdf.footer,
    )

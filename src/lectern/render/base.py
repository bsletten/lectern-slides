"""Renderer protocol, capabilities, and the adapter registry.

Adapters register themselves under a name; the CLI looks them up via
:func:`get_renderer`. ``available()`` guards adapters that shell out to an
external binary; ``capabilities()`` lets the build degrade gracefully when a
requested output format isn't supported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..config import Config
    from ..preprocess import AssembledDeck


@dataclass(frozen=True)
class Caps:
    """What output formats and features an adapter can produce."""

    html: bool = False
    pdf: bool = False
    pptx: bool = False
    embeds: bool = False


@dataclass
class RenderResult:
    """The outcome of a render: the primary artifact, copied assets, warnings."""

    output: Path
    assets: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class Renderer(Protocol):
    name: str

    def available(self) -> bool:
        """Whether this adapter can run (e.g. its external binary is present)."""
        ...

    def capabilities(self) -> Caps: ...

    def render(
        self, deck: AssembledDeck, config: Config, out_dir: Path, fmt: str = "html"
    ) -> RenderResult: ...


# Output formats a build can request, mapped to the ``Caps`` flag that gates them.
FORMATS = ("html", "pdf", "pptx")

renderers: dict[str, Renderer] = {}


def supports_format(caps: Caps, fmt: str) -> bool:
    """Whether ``caps`` advertises the requested output ``fmt``."""
    return {"html": caps.html, "pdf": caps.pdf, "pptx": caps.pptx}.get(fmt, False)


def renderers_supporting(fmt: str) -> list[str]:
    """Names of registered adapters that can produce ``fmt`` (sorted)."""
    return sorted(
        name for name, r in renderers.items() if supports_format(r.capabilities(), fmt)
    )


def register(renderer: Renderer) -> Renderer:
    """Register an adapter under ``renderer.name`` (idempotent)."""
    renderers[renderer.name] = renderer
    return renderer


def get_renderer(name: str) -> Renderer:
    try:
        return renderers[name]
    except KeyError:
        known = ", ".join(sorted(renderers)) or "(none)"
        from ..errors import ConfigError

        raise ConfigError(f"unknown renderer '{name}' (available: {known})") from None

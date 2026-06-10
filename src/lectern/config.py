"""Deck configuration (TOML) and source-entry resolution.

The pydantic model captures the v1 schema from the spec. Sub-sections
(``[serve]``, ``[reveal]``, ``[marp]``, ``[quarto]``, ``[pdf]``) are kept
permissive (``extra="allow"``) so later milestones can read their own keys
without this model needing to know them yet — and so today's sample decks, which
already carry those keys, validate.

:func:`resolve_source` turns a CLI ``SOURCE`` argument into a concrete
:class:`ResolvedSource`: the config, the root directory paths resolve against,
the ordered include entries, and the partial search dirs.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .errors import ConfigError
from .source import FilesystemSource, Source

_MANIFEST_NAMES = ("deck.toml", "lectern.toml")
_MARKDOWN_SUFFIXES = (".md", ".markdown")


class _Section(BaseModel):
    """Base for permissive config sub-sections."""

    model_config = ConfigDict(extra="allow")


class ServeConfig(_Section):
    host: str = "127.0.0.1"
    port: int = 8080
    open: bool = True
    coi: bool = False


class RevealConfig(_Section):
    controls: bool = True
    progress: bool = True
    transition: str = "none"
    highlight: bool = True
    math: str | bool = False


class Config(BaseModel):
    """The validated deck manifest."""

    model_config = ConfigDict(extra="allow")

    title: str = ""
    author: str = ""
    renderer: str = "reveal"
    theme: str = "base"
    aspect: str = "16:9"
    asset_base: str | None = None
    partials: list[str] = Field(default_factory=list)
    out_dir: str = "dist"
    build_dir: str = "build"
    max_include_depth: int = 16
    slides: list[str] | None = None

    serve: ServeConfig = Field(default_factory=ServeConfig)
    reveal: RevealConfig = Field(default_factory=RevealConfig)
    marp: dict = Field(default_factory=dict)
    quarto: dict = Field(default_factory=dict)
    pdf: dict = Field(default_factory=dict)


@dataclass
class ResolvedSource:
    """A CLI ``SOURCE`` resolved to everything the assembler needs."""

    config: Config
    root: Path  # directory that relative include paths resolve against
    entries: list[str]  # ordered include targets ("path" or "path#ranges")
    origin_display: str  # what to cite for top-level (manifest/dir) errors
    partial_dirs: list[Path] = field(default_factory=list)
    mode: str = "manifest"  # "manifest" | "directory" | "single"


def load_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid TOML in {path}: {e}") from e


def _validate(data: dict) -> Config:
    try:
        return Config.model_validate(data)
    except Exception as e:  # pydantic ValidationError → user-facing ConfigError
        raise ConfigError(f"invalid configuration: {e}") from e


def _partial_dirs(config: Config, root: Path) -> list[Path]:
    dirs: list[Path] = []
    for entry in config.partials:
        p = Path(entry).expanduser()
        dirs.append(p if p.is_absolute() else (root / p))
    return dirs


def resolve_source(
    source: str | Path,
    *,
    config_override: str | Path | None = None,
    src: Source | None = None,
) -> ResolvedSource:
    """Resolve a ``SOURCE`` argument (manifest, deck dir, or single ``.md``)."""
    src = src or FilesystemSource()
    source = Path(source).expanduser()

    data: dict = {}
    manifest_path: Path | None = None
    if config_override is not None:
        manifest_path = Path(config_override).expanduser()
        data = load_toml(manifest_path)

    if source.is_dir():
        root = source
        if manifest_path is None:
            for name in _MANIFEST_NAMES:
                candidate = source / name
                if candidate.is_file():
                    manifest_path = candidate
                    data = load_toml(candidate)
                    break
        config = _validate(data)
        if config.slides:
            entries, mode = list(config.slides), "manifest"
        else:
            entries = [p.name for p in src.list(root)]
            mode = "directory"
        origin = manifest_path.name if manifest_path else source.name

    elif source.suffix == ".toml":
        manifest_path = manifest_path or source
        if config_override is None:
            data = load_toml(source)
        root = manifest_path.parent
        config = _validate(data)
        if config.slides:
            entries, mode = list(config.slides), "manifest"
        else:
            entries = [p.name for p in src.list(root)]
            mode = "directory"
        origin = source.name

    elif source.suffix in _MARKDOWN_SUFFIXES:
        if not source.is_file():
            raise ConfigError(f"source file not found: {source}")
        root = source.parent
        config = _validate(data)
        entries, mode = [source.name], "single"
        origin = source.name

    else:
        raise ConfigError(
            f"don't know how to read source '{source}' "
            "(expected a deck directory, a .toml manifest, or a .md file)"
        )

    if not entries:
        raise ConfigError(f"no slides found for source '{source}'")

    return ResolvedSource(
        config=config,
        root=root,
        entries=entries,
        origin_display=origin,
        partial_dirs=_partial_dirs(config, root),
        mode=mode,
    )

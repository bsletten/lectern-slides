"""Deck configuration (TOML), layered precedence, and source-entry resolution.

A deck is **external** to this tool: ``SOURCE`` is an arbitrary path to a deck
that lives in its own repository. The *deck root* is the manifest's directory (or
the deck dir / the single file's parent), resolved to an absolute path. **Every
relative path in a deck's config — slides, partials, a local ``asset_base``, the
theme, ``out_dir``, ``build_dir`` — resolves against the deck root**, never the
process CWD or where Lectern is installed. Absolute paths and URLs pass through.

Config is merged from three layers, highest precedence first:

1. **CLI flags** (``cli_overrides``),
2. the deck's ``deck.toml``,
3. a **user config** at ``$XDG_CONFIG_HOME/lectern/config.toml`` (fallback
   ``~/.config/lectern/config.toml``),

over the built-in defaults baked into :class:`Config`. That lets a shared
partials library and a house theme be set once globally and inherited by every
separate deck repo. (Relative paths in the user config still resolve against each
deck's root, so global paths should be absolute or ``~``-rooted.)
"""

from __future__ import annotations

import os
import tomllib
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .errors import ConfigError
from .source import FilesystemSource, Source

_MANIFEST_NAMES = ("deck.toml", "lectern.toml")
_MARKDOWN_SUFFIXES = (".md", ".markdown")
_USER_CONFIG_SUBPATH = ("lectern", "config.toml")


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


class PdfConfig(_Section):
    """PDF export settings (see ``PDF-EXPORT.md``). All have sensible defaults;
    CLI flags and the ``ink_saver`` preset layer on top in ``pdf.options``."""

    # render-time (change the master)
    backgrounds: bool = True
    light_inverse: bool = False
    fragments: str = "flatten"  # flatten | steps
    paper: str = "deck"  # deck | letter | a4 | WxH
    posters: str = "auto"  # auto | explicit | off
    poster_at: int = 1200  # ms

    # color / B&W
    color: str = "color"  # color | bw
    bw_engine: str = "tokens"  # tokens | ghostscript
    ink_saver: bool = False

    # imposition / layout
    layout: str = "2up-notes"  # 1up | 2up | 2up-notes | 4up | 6up | 3up-notes
    orientation: str = "auto"  # auto (match deck) | portrait | landscape
    margins: str = "12mm"
    gutter: str = "10mm"
    frame: bool = True
    slide_numbers: bool = True
    header: str = ""
    footer: str = "{title} · {date} · {page}/{pages}"


class Config(BaseModel):
    """The validated, merged deck configuration."""

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
    remark_compat: bool = False
    slides: list[str] | None = None

    serve: ServeConfig = Field(default_factory=ServeConfig)
    reveal: RevealConfig = Field(default_factory=RevealConfig)
    marp: dict = Field(default_factory=dict)
    quarto: dict = Field(default_factory=dict)
    pdf: PdfConfig = Field(default_factory=PdfConfig)


@dataclass
class ResolvedSource:
    """A CLI ``SOURCE`` resolved to everything downstream needs.

    All path fields are absolute and anchored at :attr:`root` (the deck root), so
    resolution is independent of the process CWD and the install location.
    """

    config: Config
    root: Path  # absolute deck root; relative deck paths resolve against this
    entries: list[str]  # ordered include targets ("path" or "path#ranges")
    origin_display: str  # what to cite for top-level (manifest/dir) errors
    partial_dirs: list[Path] = field(default_factory=list)
    out_dir: Path = field(default_factory=lambda: Path("dist"))
    build_dir: Path = field(default_factory=lambda: Path("build"))
    mode: str = "manifest"  # "manifest" | "directory" | "single"


def user_config_path() -> Path:
    """The user-level config path, honoring ``XDG_CONFIG_HOME``."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else (Path.home() / ".config")
    return root.joinpath(*_USER_CONFIG_SUBPATH)


def load_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid TOML in {path}: {e}") from e


def _deep_merge(base: dict, over: dict) -> dict:
    """Recursively merge ``over`` onto ``base``; ``over`` wins on conflicts."""
    out = deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def _validate(data: dict) -> Config:
    try:
        return Config.model_validate(data)
    except Exception as e:  # pydantic ValidationError → user-facing ConfigError
        raise ConfigError(f"invalid configuration: {e}") from e


def _under_root(value: str, root: Path) -> Path:
    """Resolve a config path against the deck root (absolute/``~`` pass through)."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else (root / p)


def _layer(
    deck_data: dict,
    cli_overrides: dict | None,
    user_config: Path | None,
) -> dict:
    """Merge user config < deck.toml < CLI flags into one raw config dict."""
    path = user_config if user_config is not None else user_config_path()
    user_data = load_toml(path) if path.is_file() else {}
    merged = _deep_merge(user_data, deck_data)
    if cli_overrides:
        merged = _deep_merge(
            merged, {k: v for k, v in cli_overrides.items() if v is not None}
        )
    return merged


def resolve_source(
    source: str | Path,
    *,
    config_override: str | Path | None = None,
    cli_overrides: dict | None = None,
    user_config: Path | None = None,
    src: Source | None = None,
) -> ResolvedSource:
    """Resolve a ``SOURCE`` (manifest, deck dir, or single ``.md``) to a deck.

    ``cli_overrides`` is a flat dict of config keys set on the command line
    (``None`` values are ignored). ``user_config`` overrides the auto-discovered
    user config path (used in tests for isolation).
    """
    src = src or FilesystemSource()
    source = Path(source).expanduser()

    deck_data: dict = {}
    manifest_path: Path | None = None
    if config_override is not None:
        manifest_path = Path(config_override).expanduser()
        deck_data = load_toml(manifest_path)

    if source.is_dir():
        root = source
        if manifest_path is None:
            for name in _MANIFEST_NAMES:
                candidate = source / name
                if candidate.is_file():
                    manifest_path = candidate
                    deck_data = load_toml(candidate)
                    break
        origin = manifest_path.name if manifest_path else source.name
        single = None

    elif source.suffix == ".toml":
        manifest_path = manifest_path or source
        if config_override is None:
            deck_data = load_toml(source)
        root = manifest_path.parent
        origin = source.name
        single = None

    elif source.suffix in _MARKDOWN_SUFFIXES:
        if not source.is_file():
            raise ConfigError(f"source file not found: {source}")
        root = source.parent
        origin = source.name
        single = source.name

    else:
        raise ConfigError(
            f"don't know how to read source '{source}' "
            "(expected a deck directory, a .toml manifest, or a .md file)"
        )

    # Anchor the deck root absolutely: everything below is CWD-independent.
    root = root.resolve()

    config = _validate(_layer(deck_data, cli_overrides, user_config))

    if single is not None:
        entries, mode = [single], "single"
    elif config.slides:
        entries, mode = list(config.slides), "manifest"
    else:
        entries, mode = [p.name for p in src.list(root)], "directory"

    if not entries:
        raise ConfigError(f"no slides found for source '{source}'")

    return ResolvedSource(
        config=config,
        root=root,
        entries=entries,
        origin_display=origin,
        partial_dirs=[_under_root(p, root) for p in config.partials],
        out_dir=_under_root(config.out_dir, root),
        build_dir=_under_root(config.build_dir, root),
        mode=mode,
    )

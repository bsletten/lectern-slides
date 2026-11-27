"""Fence elements: render a configured code fence as a custom element.

A deck maps a fence language to a custom element in ``deck.toml``::

    [fences.ikigai]
    element = "ikigai-cell"
    scripts = ["vendor/ikigai/ikigai-cell.0123456789abcdef.js"]
    styles  = []
    files   = ["vendor/ikigai/ikigai_web_demo_bg.fedcba9876543210.wasm", …]

    [fences.ikigai.data]              # optional, emitted once in <head>
    type = "application/ikigai-kernel+json"
    file = "kernel.json"              # or: text = '''{ … }'''

A ```` ```ikigai ```` fence then renders as ``<ikigai-cell>CODE</ikigai-cell>``,
the code its escaped text content. Every other fence renders as before, and a
deck with no ``[fences]`` table builds byte-for-byte as it did without it.

The named files are local, never URLs, so a built deck stays self-contained.
They are copied together, under their own names, into one content-hashed
directory ``assets/<element>-<hash>/`` — an element's files commonly find each
other by relative URL (a script importing its glue, a glue fetching its
``.wasm``), so they are kept side by side and unrenamed; the directory name
carries the hash instead.

Lectern knows nothing about any particular element: the element, its files and
its ``data`` block (passed through untouched) are all the deck's.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ConfigError
from .source import FilesystemSource, Source

if TYPE_CHECKING:
    from .config import Config

# A valid custom-element name: lowercase ASCII start, at least one hyphen.
_ELEMENT_NAME = re.compile(r"^[a-z][a-z0-9._]*-[a-z0-9._-]*$")
_URL_PREFIXES = ("http://", "https://", "//", "data:", "ftp://", "file:")
# Directories this module writes under out_dir/assets (pruned when stale).
FENCE_DIR = re.compile(r"^[a-z][a-z0-9._-]*-[0-9a-f]{16}$")


class FenceData(BaseModel):
    """A ``<script type=…>`` data block the element reads, emitted verbatim."""

    model_config = ConfigDict(extra="forbid")

    type: str
    file: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> FenceData:
        if (self.file is None) == (self.text is None):
            raise ValueError("a fence data block takes exactly one of file= or text=")
        if not self.type or any(c in self.type for c in "\"'<>& \t\n"):
            raise ValueError(f"fence data type {self.type!r} is not a MIME type")
        return self


class FenceElement(BaseModel):
    """One ``[fences.<lang>]`` table."""

    model_config = ConfigDict(extra="forbid")

    element: str
    scripts: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    data: FenceData | None = None

    @field_validator("element")
    @classmethod
    def _custom_element(cls, value: str) -> str:
        if not _ELEMENT_NAME.match(value):
            raise ValueError(
                f"{value!r} is not a custom-element name (lowercase, with a hyphen, "
                "such as 'my-cell')"
            )
        return value


def element_map(config: Config) -> dict[str, str]:
    """Fence language (lowercased) → element name, for the lowering scanner."""
    return {lang.lower(): f.element for lang, f in config.fences.items()}


def render_element(element: str, code_lines: list[str], indent: str = "") -> list[str]:
    """The Markdown lines a fence element lowers to.

    The element sits on one line inside a ``<div>`` — a CommonMark type-6 HTML
    block, so the Markdown renderer passes it through verbatim — with the code's
    newlines written as ``&#10;`` so a blank line in the code cannot end the
    block early. The browser decodes the entities: the element's text content is
    exactly the fenced code. A blank line closes the block.

    *indent* is the opening fence's indentation (a fence inside a list item).
    As CommonMark does for a fenced code block, up to that much leading
    whitespace is stripped from each code line, so the element's text is the
    code without the list's indentation; the element line itself keeps the
    indentation so it stays inside the list item.
    """
    code = "\n".join(_dedent(line, len(indent)) for line in code_lines)
    text = html.escape(code, quote=False).replace("\r", "&#13;").replace("\n", "&#10;")
    return [
        f'{indent}<div class="lectern-fence"><{element}>{text}</{element}></div>',
        "",
    ]


def _dedent(line: str, width: int) -> str:
    """Strip up to *width* leading spaces from *line* (CommonMark fence rule)."""
    n = 0
    while n < width and n < len(line) and line[n] == " ":
        n += 1
    return line[n:]


def _href(rel_dir: str, name: str) -> str:
    """The attribute-safe, percent-encoded URL of a staged file."""
    return html.escape(quote(f"{rel_dir}/{name}", safe="/"))


def _is_url(value: str) -> bool:
    return value.strip().lower().startswith(_URL_PREFIXES)


def _local(lang: str, key: str, value: str, root: Path, src: Source) -> Path:
    if _is_url(value):
        raise ConfigError(
            f"fences.{lang}.{key}: '{value}' is a URL; fence assets are copied into "
            "the build so a deck stays self-contained, so name a local file instead"
        )
    p = Path(value).expanduser()
    path = p if p.is_absolute() else root / p
    if not src.exists(path):
        raise ConfigError(f"fences.{lang}.{key}: file not found: {value}")
    return path


@dataclass
class _Staged:
    lang: str
    fence: FenceElement
    files: dict[str, bytes]  # name in the asset directory → content
    data_text: str | None
    digest: str


def _stage(lang: str, fence: FenceElement, root: Path, src: Source) -> _Staged:
    files: dict[str, bytes] = {}
    paths: dict[str, Path] = {}
    for key in ("scripts", "styles", "files"):
        for value in getattr(fence, key):
            path = _local(lang, key, value, root, src)
            if path.name in paths and paths[path.name] != path:
                raise ConfigError(
                    f"fences.{lang}.{key}: two files are named '{path.name}'; a "
                    "fence's files share one directory, so give them distinct names"
                )
            if path.name not in files:
                paths[path.name] = path
                files[path.name] = src.read_bytes(path)

    data_text = None
    if fence.data is not None:
        if fence.data.file is not None:
            data_path = _local(lang, "data.file", fence.data.file, root, src)
            data_text = src.read(data_path)
        else:
            data_text = fence.data.text or ""
        if "</script" in data_text.lower():
            raise ConfigError(
                f"fences.{lang}.data: the block contains '</script', which would "
                "end it early; it is passed through untouched, so remove it"
            )
        if "<!--" in data_text:
            raise ConfigError(
                f"fences.{lang}.data: the block contains '<!--', which can make "
                "the browser read past its '</script>' into the rest of the page; "
                "it is passed through untouched, so remove it"
            )

    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode() + b"\0" + files[name] + b"\0")
    return _Staged(lang, fence, files, data_text, h.hexdigest()[:16])


def validate(config: Config, root: Path, src: Source | None = None) -> None:
    """Check every ``[fences]`` table's files without writing anything."""
    src = src or FilesystemSource()
    for lang, fence in config.fences.items():
        _stage(lang, fence, root, src)


@dataclass
class FenceAssets:
    """What :func:`stage` wrote: the ``<head>`` markup and the files copied."""

    head: str = ""
    copied: list[Path] = field(default_factory=list)
    dirs: list[Path] = field(default_factory=list)


def stage(
    config: Config, root: Path, out_dir: Path, src: Source | None = None
) -> FenceAssets:
    """Copy each fence's files into ``out_dir/assets`` and build its ``<head>`` tags.

    Per fence, in deck order: the data block, then the stylesheets, then the
    scripts as module scripts (the data is in place before the element upgrades).
    The files are read through *src*, the deck's :class:`~lectern.source.Source`.
    """
    src = src or FilesystemSource()
    result = FenceAssets()
    lines: list[str] = []
    for lang, fence in config.fences.items():
        staged = _stage(lang, fence, root, src)
        rel_dir = f"assets/{fence.element}-{staged.digest}"
        dest_dir = out_dir / rel_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name, content in staged.files.items():
            dest = dest_dir / name
            if not dest.is_file() or dest.read_bytes() != content:
                dest.write_bytes(content)
            result.copied.append(dest)
        result.dirs.append(dest_dir)

        if staged.data_text is not None and fence.data is not None:
            lines.append(f'<script type="{fence.data.type}">')
            lines.append(staged.data_text.rstrip("\n"))
            lines.append("</script>")
        for value in fence.styles:
            href = _href(rel_dir, Path(value).expanduser().name)
            lines.append(f'<link rel="stylesheet" href="{href}">')
        for value in fence.scripts:
            href = _href(rel_dir, Path(value).expanduser().name)
            lines.append(f'<script type="module" src="{href}"></script>')
    result.head = "\n".join(lines)
    return result

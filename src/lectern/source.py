"""The ``Source`` seam.

``Source`` is the abstraction that lets a future CMS/graph backend replace the
filesystem without touching preprocess/render/serve. Nothing downstream should
read files directly — it goes through a ``Source``. For v1 the only
implementation is :class:`FilesystemSource`; a ``CmsSource`` will implement the
same protocol against the semantic graph later.

Path *resolution policy* (relative-then-search-paths) lives in the preprocess
layer; ``Source`` only does the raw read/exists/list against already-chosen
locations, which keeps the protocol narrow enough for a graph backend to honor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Source(Protocol):
    """Read content and enumerate slide files for a deck."""

    def read(self, path: Path) -> str:
        """Return the text contents at *path*."""
        ...

    def exists(self, path: Path) -> bool:
        """Whether *path* names an existing readable item."""
        ...

    def list(self, directory: Path) -> list[Path]:
        """Return the deck's Markdown files under *directory*, in stable order."""
        ...


class FilesystemSource:
    """The default v1 source: plain files on disk."""

    def read(self, path: Path) -> str:
        return Path(path).read_text(encoding="utf-8")

    def exists(self, path: Path) -> bool:
        return Path(path).is_file()

    def list(self, directory: Path) -> list[Path]:
        # Directory mode: lexical filename order (zero-padded prefixes recommended).
        return sorted(p for p in Path(directory).glob("*.md") if p.is_file())

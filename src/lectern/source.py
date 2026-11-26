"""The ``Source`` seam.

``Source`` is the abstraction that lets a CMS/graph backend replace the
filesystem without touching preprocess/render/serve. Nothing downstream should
read deck content directly — slide Markdown, themes, and assets all go through a
``Source``. :class:`FilesystemSource` is the default; :class:`KernelSource`
answers from kernel resources.

A source is keyed by a :data:`Key`: either a ``Path`` (the deck-relative layout
every deck has) or an IRI string (``"urn:…"``, ``"https://…"``, …), which is how
a graph backend names its nodes. A path-keyed request against a graph backend is
mapped onto an IRI by that backend; an IRI-keyed request against the filesystem
accepts ``file:`` IRIs.

Path *resolution policy* (relative-then-search-paths) lives in the preprocess
layer; ``Source`` only does the raw read/exists/list against already-chosen
locations, which keeps the protocol narrow enough for a graph backend to honor.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable
from urllib.parse import quote, unquote, urlsplit

#: A source key: a filesystem-style path, or an IRI string.
Key = Path | str

# RFC 3987 scheme: ALPHA *( ALPHA / DIGIT / "+" / "-" / "." ) ":" — at least two
# characters so a Windows drive letter (``C:\…``) never reads as an IRI.
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]+:")


def is_iri(key: Key) -> bool:
    """Whether *key* is an IRI string (vs a path)."""
    return isinstance(key, str) and bool(_SCHEME.match(key))


@runtime_checkable
class Source(Protocol):
    """Read content and enumerate slide files for a deck."""

    def read(self, key: Key) -> str:
        """Return the text contents at *key* (a path or an IRI)."""
        ...

    def read_bytes(self, key: Key) -> bytes:
        """Return the raw bytes at *key* (assets, which may be binary)."""
        ...

    def exists(self, key: Key) -> bool:
        """Whether *key* names an existing readable item."""
        ...

    def list(self, directory: Key) -> list[Path]:
        """Return the deck's Markdown files under *directory*, in stable order."""
        ...


class FilesystemSource:
    """The default source: plain files on disk. IRIs must be ``file:`` IRIs."""

    @staticmethod
    def _path(key: Key) -> Path:
        if is_iri(key):
            parts = urlsplit(str(key))
            if parts.scheme.lower() != "file":
                raise ValueError(f"filesystem source cannot read IRI {key!r}")
            return Path(unquote(parts.path))
        return Path(key)

    def read(self, key: Key) -> str:
        return self._path(key).read_text(encoding="utf-8")

    def read_bytes(self, key: Key) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: Key) -> bool:
        try:
            return self._path(key).is_file()
        except ValueError:
            return False

    def list(self, directory: Key) -> list[Path]:
        # Directory mode: lexical filename order (zero-padded prefixes recommended).
        d = self._path(directory)
        return sorted(p for p in d.glob("*.md") if p.is_file())


class KernelResources(Protocol):
    """The slice of the kernel's Python face a :class:`KernelSource` needs.

    ``get`` returns a resource's bytes by IRI (``None`` when there is none);
    ``list`` returns the IRIs of the resources directly under a container IRI.
    """

    def get(self, iri: str) -> bytes | None: ...

    def list(self, container: str) -> Iterable[str]: ...


class KernelSource:
    """A source that answers from kernel resources, keyed by IRI.

    The deck lives under one *base* IRI (``urn:deck:ai-sec/``, say). Lectern still
    lays a deck out as paths under a deck root — manifests, includes, ``partials``
    search paths and asset refs are all path-shaped — so the source maps each path
    under *root* onto ``base`` + the path relative to *root*; an IRI key is passed
    to the kernel unchanged. *root* is a virtual directory: nothing is read from
    disk, so a deck whose slides, theme and assets all come from the kernel needs
    no local files.

    *resources* is anything with ``get(iri) -> bytes | None`` and
    ``list(container_iri) -> iterable of IRIs`` (:class:`KernelResources`). That
    keeps lectern free of a hard dependency on the kernel's Python bindings: hand
    in the kernel's resource client, or :meth:`from_mapping` for an in-memory set.
    """

    def __init__(
        self,
        resources: KernelResources,
        base: str,
        root: Path = Path("/kernel/deck"),
    ):
        if not is_iri(base):
            raise ValueError(f"kernel source base must be an IRI, got {base!r}")
        self.resources = resources
        self.base = base if base.endswith(("/", ":")) else base + "/"
        self.root = Path(root)

    @classmethod
    def from_mapping(
        cls, items: dict[str, bytes | str], base: str, root: Path = Path("/kernel/deck")
    ) -> KernelSource:
        """A kernel source over an in-memory ``{iri: content}`` mapping."""
        return cls(_MappingResources(items), base, root)

    # -- key mapping --------------------------------------------------------

    def iri(self, key: Key) -> str | None:
        """The IRI a key names, or ``None`` for a path outside the deck root."""
        if is_iri(key):
            return str(key)
        p = PurePosixPath(Path(key).as_posix())
        root = PurePosixPath(self.root.as_posix())
        try:
            rel = p.relative_to(root)
        except ValueError:
            return None
        parts = [s for s in rel.parts if s not in ("", ".")]
        if ".." in parts:
            return None
        return self.base + "/".join(quote(s, safe="@!$&'()*+,;=-._~") for s in parts)

    def path(self, iri: str) -> Path | None:
        """The deck path an IRI under *base* maps to (the inverse of :meth:`iri`)."""
        if not iri.startswith(self.base):
            return None
        rel = iri[len(self.base) :]
        return self.root.joinpath(*[unquote(s) for s in rel.split("/") if s])

    # -- Source -------------------------------------------------------------

    def _get(self, key: Key) -> bytes | None:
        iri = self.iri(key)
        return None if iri is None else self.resources.get(iri)

    def read_bytes(self, key: Key) -> bytes:
        data = self._get(key)
        if data is None:
            raise FileNotFoundError(f"no kernel resource for {key}")
        return data

    def read(self, key: Key) -> str:
        return self.read_bytes(key).decode("utf-8")

    def exists(self, key: Key) -> bool:
        return self._get(key) is not None

    def list(self, directory: Key) -> list[Path]:
        container = self.iri(directory)
        if container is None:
            return []
        if not container.endswith("/"):
            container += "/"
        out: list[Path] = []
        for iri in self.resources.list(container):
            rel = iri[len(container) :] if iri.startswith(container) else None
            if not rel or "/" in rel or not rel.endswith(".md"):
                continue
            p = self.path(iri)
            if p is not None:
                out.append(p)
        return sorted(out)


class _MappingResources:
    """``KernelResources`` over a dict (tests, and decks staged in memory)."""

    def __init__(self, items: dict[str, bytes | str]):
        self._items = {
            k: v.encode("utf-8") if isinstance(v, str) else bytes(v)
            for k, v in items.items()
        }

    def get(self, iri: str) -> bytes | None:
        return self._items.get(iri)

    def list(self, container: str) -> list[str]:
        return [k for k in self._items if k.startswith(container)]

"""User-facing error hierarchy.

Every error that can be traced to the author's source carries a
:class:`~lectern.sourcemap.SourceLocation` so the CLI can report a
``file:line`` (or ``file``) the author can act on, never an internal offset.
"""

from __future__ import annotations

from .sourcemap import SourceLocation


class LecternError(Exception):
    """Base for all errors meant to be shown to the user.

    ``location`` is the originating source location (a file, optionally a line),
    when one is known. ``render`` produces the single-line message the CLI prints.
    """

    def __init__(self, message: str, *, location: SourceLocation | None = None):
        super().__init__(message)
        self.message = message
        self.location = location

    def render(self) -> str:
        if self.location is not None:
            return f"{self.location}: {self.message}"
        return self.message


class ConfigError(LecternError):
    """Manifest/config could not be loaded or validated."""


class IncludeError(LecternError):
    """An ``include`` directive could not be resolved to a file."""


class RangeError(LecternError):
    """A ``#1-3,14`` slide-range specification was malformed or out of bounds."""


class CycleError(LecternError):
    """An include cycle was detected (a file transitively includes itself)."""


class DepthError(LecternError):
    """``max_include_depth`` was exceeded."""

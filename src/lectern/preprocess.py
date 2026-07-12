"""Assemble: expand includes/ranges/partials into one deck with a source-map.

This is Phase 0 — the whole point and the most reusable layer. Given a resolved
source it produces an :class:`AssembledDeck`: a flat list of :class:`OutLine`
(text + provenance), which is simultaneously the assembled Markdown and its
source-map.

Resolution rules (spec §3):

* include directives are HTML comments — ``<!-- include: PATH -->`` or
  ``<!-- include: PATH#RANGES -->`` — so raw ``.md`` stays valid CommonMark;
* PATH resolves (1) relative to the including file, then (2) each ``partials``
  search dir, in order; otherwise an error citing the directive's location;
* RANGES select 1-based slides within the included file (fence-aware ``---``);
* nested includes are allowed; cycles (a file in its own ancestor chain) and
  ``max_include_depth`` are guarded;
* each contributed slide is prefixed with a ``<!-- @from PATH slide=N -->``
  provenance comment;
* an included file's own frontmatter is ignored for content (warn if non-empty).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from .config import ResolvedSource, resolve_source
from .errors import CycleError, DepthError, IncludeError, RangeError
from .ranges import parse_ranges
from .remark_compat import normalize_remark_slide
from .slides import closes_fence, fence_marker, split_slides
from .source import FilesystemSource, Source
from .sourcemap import OutLine, SourceLocation, SourceMap

# An include directive occupying its own line (indentation tolerated).
_INCLUDE_RE = re.compile(r"^\s*<!--\s*include:\s*(?P<target>.+?)\s*-->\s*$")
_PROVENANCE_PREFIX = "<!-- @from "


@dataclass
class _Ctx:
    """Shared, mutable state threaded through one assemble run."""

    source: Source
    root: Path
    partial_dirs: list[Path]
    max_depth: int
    origin_display: str
    asset_dirs: list[Path] = field(default_factory=list)
    remark_compat: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class AssembledDeck:
    """The assembled deck and its provenance."""

    outlines: list[OutLine]
    warnings: list[str]
    config: object  # lectern.config.Config (avoid import cycle in annotations)
    root: Path
    theme_dirs: list[Path] = field(default_factory=list)  # resolved theme search dirs

    def markdown(self, *, provenance: bool = True) -> str:
        """Render the assembled Markdown.

        With ``provenance=False`` the ``<!-- @from ... -->`` comments are dropped
        — what a renderer that would otherwise display them should consume.
        """
        lines = (
            o.text
            for o in self.outlines
            if provenance or not o.text.startswith(_PROVENANCE_PREFIX)
        )
        return "\n".join(lines) + "\n"

    @property
    def sourcemap(self) -> SourceMap:
        return SourceMap([o.loc for o in self.outlines])

    @property
    def slide_count(self) -> int:
        if not self.outlines:
            return 0
        return sum(1 for o in self.outlines if o.is_separator) + 1

    def slides(self) -> list[list[OutLine]]:
        """Split the output into slides on the synthetic separators."""
        groups: list[list[OutLine]] = [[]]
        for o in self.outlines:
            if o.is_separator:
                groups.append([])
            else:
                groups[-1].append(o)
        return groups


def assemble(
    source: str | Path,
    *,
    config_override: str | Path | None = None,
    cli_overrides: dict | None = None,
    user_config: Path | None = None,
    src: Source | None = None,
) -> AssembledDeck:
    """Assemble the deck named by *source* into an :class:`AssembledDeck`."""
    src = src or FilesystemSource()
    resolved = resolve_source(
        source,
        config_override=config_override,
        cli_overrides=cli_overrides,
        user_config=user_config,
        src=src,
    )
    return assemble_resolved(resolved, src=src)


def assemble_resolved(
    resolved: ResolvedSource, *, src: Source | None = None
) -> AssembledDeck:
    """Assemble from an already-resolved source (the testable seam)."""
    src = src or FilesystemSource()
    # A local `asset_base` is also an include search dir, so a themed SVG kept
    # where assets live (`_assets/…`) can be inlined with the same path used to
    # reference it as an image. A URL `asset_base` has no local dir to read from.
    asset_dirs: list[Path] = []
    asset_base = resolved.config.asset_base
    if asset_base and not asset_base.lower().startswith(("http://", "https://", "//")):
        base = Path(asset_base).expanduser()
        asset_dirs = [base if base.is_absolute() else (resolved.root / base)]
    ctx = _Ctx(
        source=src,
        root=resolved.root,
        partial_dirs=resolved.partial_dirs,
        asset_dirs=asset_dirs,
        max_depth=resolved.config.max_include_depth,
        origin_display=resolved.origin_display,
        remark_compat=getattr(resolved.config, "remark_compat", False),
    )

    # Each top-level entry is itself an include resolved against the deck root,
    # so frontmatter handling, ranges, and provenance are uniform everywhere.
    groups = [
        _resolve_include(entry, resolved.origin_display, resolved.root, None, [], ctx)
        for entry in resolved.entries
    ]
    outlines = _join_groups(groups, SourceLocation(resolved.origin_display))
    return AssembledDeck(
        outlines=outlines,
        warnings=ctx.warnings,
        config=resolved.config,
        root=resolved.root,
        theme_dirs=resolved.theme_dirs,
    )


def _resolve_include(
    target: str,
    including_display: str,
    including_dir: Path,
    directive_line: int | None,
    stack: list[Path],
    ctx: _Ctx,
) -> list[OutLine]:
    """Resolve one include target into a flat OutLine list (with provenance)."""
    loc = SourceLocation(including_display, directive_line)
    path_text, ranges_text = _split_target(target)

    resolved = _resolve_path(path_text, including_dir, ctx, loc)

    if resolved in stack:
        chain = " -> ".join(_display(p, ctx.root) for p in (*stack, resolved))
        raise CycleError(f"include cycle: {chain}", location=loc)
    if len(stack) >= ctx.max_depth:
        raise DepthError(
            f"max include depth ({ctx.max_depth}) exceeded at "
            f"'{_display(resolved, ctx.root)}'",
            location=loc,
        )

    raw = ctx.source.read(resolved)
    metadata, body, body_line = _split_frontmatter(raw)
    display = _display(resolved, ctx.root)

    # Inlining an SVG (`<!-- include: art.svg -->`) lets it read the slide's theme
    # tokens, which a flat `<img>` can't. But the deck is rendered by reveal's
    # client-side Markdown (marked), which only leaves markup untouched — as a raw
    # HTML block — when the opening tag both starts a line and is *complete on that
    # line*. A real-world Illustrator export breaks every part of that: the `<svg …>`
    # tag is wrapped across lines, children are tab-indented (read as an indented
    # code block), there's an embedded `<style>`, and path `d="…"` attributes span
    # lines. marked then parses the whole thing as inline HTML inside a `<p>`,
    # auto-closes `<svg>` empty, and orphans every child — the graphic vanishes.
    # Collapsing the file onto a single line sidesteps all of it at once: the
    # element becomes one complete HTML block (the shape hand-authored SVGs already
    # have). Whitespace runs — newlines included — are insignificant between SVG/XML
    # nodes and inside path data, so a single-space join is safe. (Not done for
    # Markdown partials, where blank lines separate paragraphs.)
    if resolved.suffix.lower() in (".svg", ".xml"):
        body = " ".join(ln.strip() for ln in body.split("\n") if ln.strip())
    if metadata:
        keys = ", ".join(map(str, metadata))
        ctx.warnings.append(
            f"{display}: ignoring frontmatter ({keys}); config comes from the "
            "deck manifest, not included files"
        )

    file_slides = split_slides(body, body_line)
    if ranges_text:
        try:
            indices = parse_ranges(ranges_text, len(file_slides))
        except RangeError as e:
            raise RangeError(f"{e.message} in '{display}'", location=loc) from e
    else:
        indices = list(range(1, len(file_slides) + 1))

    child_stack = [*stack, resolved]
    child_dir = resolved.parent
    groups: list[list[OutLine]] = []
    for n in indices:
        slide = file_slides[n - 1]
        provenance = OutLine(
            f"{_PROVENANCE_PREFIX}{display} slide={n} -->",
            SourceLocation(display, slide.start_line),
        )
        text = slide.text
        if ctx.remark_compat:
            text, warns = normalize_remark_slide(text)
            ctx.warnings.extend(f"{display} slide={n}: {w}" for w in warns)
        body_lines = _expand_lines(
            text, display, child_dir, child_stack, ctx, slide.start_line
        )
        groups.append([provenance, *body_lines])

    return _join_groups(groups, SourceLocation(display))


def _expand_lines(
    text: str,
    display: str,
    base_dir: Path,
    stack: list[Path],
    ctx: _Ctx,
    start_line: int,
) -> list[OutLine]:
    """Expand include directives in one slide's text (fence-aware)."""
    out: list[OutLine] = []
    fence = None
    for offset, line in enumerate(text.split("\n")):
        lineno = start_line + offset

        if fence is None:
            match = _INCLUDE_RE.match(line)
            if match is not None:
                out.extend(
                    _resolve_include(
                        match.group("target"), display, base_dir, lineno, stack, ctx
                    )
                )
                continue
            marker = fence_marker(line)
            if marker is not None:
                fence = marker
        elif closes_fence(line, fence):
            fence = None

        out.append(OutLine(line, SourceLocation(display, lineno)))

    return out


def _join_groups(groups: list[list[OutLine]], sep_loc: SourceLocation) -> list[OutLine]:
    """Concatenate slide groups, inserting a ``---`` separator between them."""
    out: list[OutLine] = []
    for group in groups:
        if out:
            out.append(OutLine("---", sep_loc, is_separator=True))
        out.extend(group)
    return out


def _split_target(target: str) -> tuple[str, str | None]:
    """Split ``path#ranges`` into ``(path, ranges)``."""
    if "#" in target:
        path, _, ranges = target.partition("#")
        return path.strip(), ranges.strip()
    return target.strip(), None


def _resolve_path(
    path_text: str, including_dir: Path, ctx: _Ctx, loc: SourceLocation
) -> Path:
    """Resolve a PATH against the including dir, the partials, then asset_base."""
    candidate = Path(path_text).expanduser()
    if candidate.is_absolute():
        search = [candidate]
    else:
        search = [including_dir / candidate]
        search += [d / candidate for d in ctx.partial_dirs]
        search += [d / candidate for d in ctx.asset_dirs]

    for c in search:
        if ctx.source.exists(c):
            return c.resolve()

    tried = ", ".join(str(c) for c in search)
    raise IncludeError(
        f"cannot resolve include '{path_text}' (tried: {tried})", location=loc
    )


def _split_frontmatter(text: str) -> tuple[dict, str, int]:
    """Return (metadata, body, body_start_line).

    Uses python-frontmatter for parsing but recovers the body's 1-based starting
    line itself, so locations stay accurate after the block is stripped.

    Frontmatter must open on the very first line. python-frontmatter strips
    leading whitespace before it looks for the ``---`` fence, so without this
    guard a slide that opens with a blank line and a ``---`` separator (a plain
    horizontal rule) would be misread as a YAML block — and the markdown below
    it fed to the YAML parser. Only parse frontmatter when line 1 is ``---``.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        # No frontmatter: return the body as python-frontmatter would (stripped),
        # so this guard changes only *detection*, never the emitted body.
        return {}, text.strip(), 1

    metadata, body = frontmatter.parse(text)

    body_line = 1
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            body_line = i + 2  # first body line follows the closing delimiter
            break

    return metadata, body, body_line


def _display(path: Path, root: Path) -> str:
    """A stable, author-facing path for *path*, relative to the deck root."""
    try:
        return Path(os.path.relpath(path, root)).as_posix()
    except ValueError:
        return str(path)

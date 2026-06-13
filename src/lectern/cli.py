"""The ``lectern`` command-line interface.

Commands so far:

* ``lectern assemble SOURCE [-o OUT]`` — expand includes/ranges into one deck and
  write the assembled Markdown (the "assemble then feed any renderer" escape
  hatch). Provenance comments are kept so the output is self-describing.
* ``lectern check SOURCE`` — validate includes/ranges (and surface warnings)
  without writing anything.
* ``lectern build SOURCE [-f html|pdf|pptx]`` — assemble and render to ``out_dir``
  via the configured adapter (reveal/remark are native HTML; marp/quarto shell out
  to their binaries — marp also does pdf/pptx). The requested format is gated by
  the adapter's capabilities, with a hint toward an adapter that supports it.
* ``lectern watch SOURCE`` — serve a live, reloading preview.
* ``lectern config SOURCE`` — show the effective merged config (CLI > deck.toml >
  user config > defaults) and where each value came from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from . import __version__
from .config import resolve_source
from .errors import ConfigError, LecternError
from .preprocess import assemble, assemble_resolved
from .render import (
    FORMATS,
    get_renderer,
    renderers_supporting,
    supports_format,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Assemble Markdown slide sources into a deck and render it.",
)


def _fail(error: LecternError) -> typer.Exit:
    typer.secho(f"error: {error.render()}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


def _emit_warnings(warnings: list[str]) -> None:
    for w in warnings:
        typer.secho(f"warning: {w}", fg=typer.colors.YELLOW, err=True)


def _assembly_overrides(
    remark_compat: bool | None,
    partials: list[str] | None,
    max_include_depth: int | None,
    aspect: str | None = None,
) -> dict:
    """Build the config-override dict for assembly/resolution flags.

    A ``--partial`` list *replaces* the configured ``partials`` for this run
    (CLI wins; lists are not merged).
    """
    overrides: dict = {}
    if remark_compat is not None:
        overrides["remark_compat"] = remark_compat
    if partials:
        overrides["partials"] = list(partials)
    if max_include_depth is not None:
        overrides["max_include_depth"] = max_include_depth
    if aspect is not None:
        overrides["aspect"] = aspect
    return overrides


_SECTION_KEYS = ("serve", "reveal", "marp", "quarto", "pdf")
_LAYER_LABEL = {"cli": "cli", "deck": "deck.toml", "user": "user"}


def _leaf_origin(keys: list[str], layers: dict[str, dict]) -> str:
    """Which layer (highest precedence) last set the value at ``keys``."""
    for name in ("cli", "deck", "user"):
        cur = layers.get(name) or {}
        ok = True
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok:
            return _LAYER_LABEL[name]
    return "default"


def _titleize(name: str) -> str:
    """A human title from a directory name (``my-talk`` -> ``My Talk``)."""
    cleaned = name.replace("-", " ").replace("_", " ").strip()
    return cleaned.title() if cleaned else "My Deck"


def _user_config_str(key: str) -> str | None:
    """A string value from the user config (``~/.config/lectern/config.toml``), if
    set — so ``new`` can inherit it (author, theme) rather than baking a default
    into the deck, which would shadow the user config (deck.toml beats it)."""
    from .config import load_toml, user_config_path

    path = user_config_path()
    if not path.is_file():
        return None
    try:
        data = load_toml(path)
    except LecternError:
        return None  # a malformed user config is reported by other commands
    value = data.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


_TITLE_SLIDE = """\
<!-- slide: .center .middle -->

# {title}

A new deck, assembled by Lectern.
"""

_CONTENT_SLIDE = """\
# Getting Started

- Edit these slides in `slides/`, and list them in `deck.toml`.
- Live, reloading preview: `lectern watch {where}`
- Build static HTML:       `lectern build {where}`
- Export a PDF:            `lectern build {where} -f pdf`
"""


@app.command(name="new")
def new_cmd(
    directory: Path = typer.Argument(
        Path("."),
        metavar="[DIRECTORY]",
        help="Where to scaffold the deck — created if missing (default: current dir).",
    ),
    title: str | None = typer.Option(
        None, "--title", help="Deck title (default: derived from the directory name)."
    ),
    author: str | None = typer.Option(
        None,
        "--author",
        help="Author name. Default: your user config's author, else 'Deck Author'.",
    ),
    theme: str | None = typer.Option(
        None,
        "-t",
        "--theme",
        help="Theme. Default: your user config's theme, else 'base'.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite deck.toml / starter slides if they exist."
    ),
) -> None:
    """Scaffold a new deck (deck.toml + a couple of slides) in DIRECTORY."""
    target = directory.expanduser()
    where = str(directory)  # echo next-step commands with what the user typed

    deck_toml = target / "deck.toml"
    slides_dir = target / "slides"
    title_md = slides_dir / "00-title.md"
    content_md = slides_dir / "10-content.md"

    existing = [p for p in (deck_toml, title_md, content_md) if p.exists()]
    if existing and not force:
        names = ", ".join(p.name for p in existing)
        raise _fail(
            ConfigError(
                f"would overwrite existing file(s): {names} — pass --force to replace"
            )
        )

    deck_title = title or _titleize(target.resolve().name)

    # Author / theme: an explicit flag wins; otherwise inherit from the user
    # config rather than baking a value in — a value in deck.toml would shadow the
    # user config (deck.toml beats it). Only fall back to a placeholder/default
    # when there's nothing to inherit.
    inherited = None if author else _user_config_str("author")
    if author:
        author_line = f'author   = "{author}"'
    elif inherited:
        author_line = (
            "# author is inherited from your user config "
            "(~/.config/lectern/config.toml)"
        )
    else:
        author_line = (
            'author   = "Deck Author"   '
            "# your name, or set it once in ~/.config/lectern/config.toml"
        )

    inherited_theme = None if theme else _user_config_str("theme")
    if theme:
        theme_line = f'theme    = "{theme}"'
    elif inherited_theme:
        theme_line = (
            "# theme is inherited from your user config (~/.config/lectern/config.toml)"
        )
    else:
        theme_line = 'theme    = "base"'

    deck = (
        f'title    = "{deck_title}"\n'
        f"{author_line}\n"
        'renderer = "reveal"\n'
        f"{theme_line}\n"
        'aspect   = "16:9"\n'
        "\n"
        "slides = [\n"
        '  "slides/00-title.md",\n'
        '  "slides/10-content.md",\n'
        "]\n"
    )

    slides_dir.mkdir(parents=True, exist_ok=True)
    deck_toml.write_text(deck, encoding="utf-8")
    title_md.write_text(_TITLE_SLIDE.format(title=deck_title), encoding="utf-8")
    content_md.write_text(_CONTENT_SLIDE.format(where=where), encoding="utf-8")

    typer.secho(f"scaffolded a new deck in {target.resolve()}", fg=typer.colors.GREEN)
    typer.echo("  + deck.toml")
    typer.echo("  + slides/00-title.md")
    typer.echo("  + slides/10-content.md")
    if inherited:
        typer.echo(f"  author inherited from your user config: {inherited}")
    elif not author:
        typer.echo(
            '  author: "Deck Author" — set `author = "…"` in '
            "~/.config/lectern/config.toml to reuse it across decks"
        )
    if inherited_theme:
        typer.echo(f"  theme inherited from your user config: {inherited_theme}")
    typer.secho("\nnext:", bold=True)
    typer.echo(f"  lectern watch {where}")


@app.command(name="assemble")
def assemble_cmd(
    source: Path = typer.Argument(
        ..., metavar="SOURCE", help="Manifest, deck dir, or .md file."
    ),
    out: Path | None = typer.Option(
        None, "-o", "--out", help="Write assembled Markdown here (default: stdout)."
    ),
    remark_compat: bool | None = typer.Option(
        None,
        "--remark-compat/--no-remark-compat",
        help="Normalize legacy Remark syntax.",
    ),
    partial: list[str] = typer.Option(
        None, "--partial", help="Replace the partials search dirs (repeatable)."
    ),
    max_include_depth: int | None = typer.Option(
        None, "--max-include-depth", help="Max nested-include depth."
    ),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Expand includes/ranges/partials into a single assembled deck."""
    overrides = _assembly_overrides(remark_compat, partial, max_include_depth)
    try:
        deck = assemble(source, config_override=config, cli_overrides=overrides)
    except LecternError as e:
        raise _fail(e) from None

    _emit_warnings(deck.warnings)
    text = deck.markdown(provenance=True)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        typer.secho(
            f"assembled {deck.slide_count} slide(s) -> {out}",
            fg=typer.colors.GREEN,
            err=True,
        )
    else:
        sys.stdout.write(text)


@app.command()
def check(
    source: Path = typer.Argument(
        ..., metavar="SOURCE", help="Manifest, deck dir, or .md file."
    ),
    remark_compat: bool | None = typer.Option(
        None,
        "--remark-compat/--no-remark-compat",
        help="Normalize legacy Remark syntax.",
    ),
    partial: list[str] = typer.Option(
        None, "--partial", help="Replace the partials search dirs (repeatable)."
    ),
    max_include_depth: int | None = typer.Option(
        None, "--max-include-depth", help="Max nested-include depth."
    ),
    a11y: bool = typer.Option(
        True, "--a11y/--no-a11y", help="Run accessibility checks (default on)."
    ),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Validate includes, ranges, and partials (and accessibility) without rendering."""
    overrides = _assembly_overrides(remark_compat, partial, max_include_depth)
    try:
        deck = assemble(source, config_override=config, cli_overrides=overrides)
    except LecternError as e:
        raise _fail(e) from None

    _emit_warnings(deck.warnings)
    a11y_warnings = []
    if a11y:
        from .a11y import audit

        a11y_warnings = audit(deck)
        _emit_warnings(f"a11y: {w}" for w in a11y_warnings)

    issues = len(deck.warnings) + len(a11y_warnings)
    suffix = f" with {issues} warning(s)" if issues else ""
    typer.secho(
        f"ok: {deck.slide_count} slide(s) assembled cleanly{suffix}",
        fg=typer.colors.GREEN,
    )


@app.command()
def build(
    source: Path = typer.Argument(
        ..., metavar="SOURCE", help="Manifest, deck dir, or .md file."
    ),
    renderer: str | None = typer.Option(
        None, "-r", "--renderer", help="Override the renderer (e.g. reveal)."
    ),
    theme: str | None = typer.Option(
        None, "-t", "--theme", help="Override the theme (bundled name or path)."
    ),
    asset_base: str | None = typer.Option(
        None, "--asset-base", help="Override the asset base (local dir or URL)."
    ),
    aspect: str | None = typer.Option(
        None, "--aspect", help="Override the aspect ratio (e.g. 16:9, 4:3, 1280x720)."
    ),
    remark_compat: bool | None = typer.Option(
        None,
        "--remark-compat/--no-remark-compat",
        help="Normalize legacy Remark syntax.",
    ),
    partial: list[str] = typer.Option(
        None, "--partial", help="Replace the partials search dirs (repeatable)."
    ),
    max_include_depth: int | None = typer.Option(
        None, "--max-include-depth", help="Max nested-include depth."
    ),
    out: Path | None = typer.Option(
        None,
        "-o",
        "--out",
        help="Override the output directory (default: deck out_dir).",
    ),
    fmt: str = typer.Option(
        "html", "-f", "--format", help="Output format: html | pdf | pptx | outline."
    ),
    layout: str | None = typer.Option(
        None,
        "--layout",
        help="PDF layout: 1up | 2up | 2up-notes | 4up | 6up | 3up-notes.",
    ),
    bw: bool = typer.Option(False, "--bw", help="PDF: grayscale output."),
    backgrounds: bool | None = typer.Option(
        None, "--backgrounds/--no-backgrounds", help="PDF: keep slide backgrounds."
    ),
    light_inverse: bool = typer.Option(
        False, "--light-inverse", help="PDF: flip dark slides to light for ink economy."
    ),
    ink_saver: bool = typer.Option(
        False, "--ink-saver", help="PDF: bw + no backgrounds + light inverse."
    ),
    paper: str | None = typer.Option(
        None, "--paper", help="PDF paper: deck | letter | a4 | WxH."
    ),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Assemble and render the deck into the deck's output dir."""
    pdf_over: dict = {}
    if layout is not None:
        pdf_over["layout"] = layout
    if bw:
        pdf_over["color"] = "bw"
    if backgrounds is not None:
        pdf_over["backgrounds"] = backgrounds
    if light_inverse:
        pdf_over["light_inverse"] = True
    if ink_saver:
        pdf_over["ink_saver"] = True
    if paper is not None:
        pdf_over["paper"] = paper

    overrides = {
        "renderer": renderer,
        "theme": theme,
        "asset_base": asset_base,
        "out_dir": str(out) if out is not None else None,
        "pdf": pdf_over or None,
        **_assembly_overrides(remark_compat, partial, max_include_depth, aspect),
    }
    try:
        if fmt not in FORMATS:
            raise ConfigError(
                f"unknown output format '{fmt}' (expected one of: {', '.join(FORMATS)})"
            )
        resolved = resolve_source(
            source, config_override=config, cli_overrides=overrides
        )

        if fmt == "outline":
            from .outline import build_outline

            deck = assemble_resolved(resolved)
            resolved.out_dir.mkdir(parents=True, exist_ok=True)
            output = resolved.out_dir / "outline.md"
            output.write_text(build_outline(deck, resolved.config), encoding="utf-8")
            _emit_warnings(deck.warnings)
            typer.secho(
                f"wrote outline of {deck.slide_count} slide(s) -> {output}",
                fg=typer.colors.GREEN,
            )
            return

        adapter = get_renderer(resolved.config.renderer)
        if not supports_format(adapter.capabilities(), fmt):
            alt = renderers_supporting(fmt)
            hint = f" (try renderer: {', '.join(alt)})" if alt else ""
            raise ConfigError(f"renderer '{adapter.name}' cannot produce '{fmt}'{hint}")
        if not adapter.available():
            raise ConfigError(
                f"renderer '{adapter.name}' is not available "
                "(its external tool is not installed or not on PATH)"
            )

        deck = assemble_resolved(resolved)
        result = adapter.render(deck, resolved.config, resolved.out_dir, fmt)
    except LecternError as e:
        raise _fail(e) from None

    _emit_warnings(result.warnings)
    pruned = f", pruned {result.pruned} stale" if result.pruned else ""
    typer.secho(
        f"built {deck.slide_count} slide(s), {len(result.assets)} asset(s)"
        f"{pruned} -> {result.output}",
        fg=typer.colors.GREEN,
    )


@app.command()
def watch(
    source: Path = typer.Argument(
        ..., metavar="SOURCE", help="Manifest, deck dir, or .md file."
    ),
    host: str | None = typer.Option(None, "--host", help="Bind host."),
    port: int | None = typer.Option(None, "--port", help="Bind port."),
    open_browser: bool | None = typer.Option(
        None, "--open/--no-open", help="Open a browser on start."
    ),
    browser: str | None = typer.Option(
        None,
        "--browser",
        help="Which browser to open (e.g. chrome, firefox, safari). Default: system.",
    ),
    coi: bool | None = typer.Option(
        None, "--coi/--no-coi", help="Send COOP/COEP isolation headers."
    ),
    renderer: str | None = typer.Option(
        None,
        "-r",
        "--renderer",
        help="Override the renderer (reveal/remark/marp/quarto).",
    ),
    theme: str | None = typer.Option(
        None, "-t", "--theme", help="Override the theme (bundled name or path)."
    ),
    asset_base: str | None = typer.Option(
        None, "--asset-base", help="Override the asset base (local dir or URL)."
    ),
    aspect: str | None = typer.Option(
        None, "--aspect", help="Override the aspect ratio (e.g. 16:9, 4:3, 1280x720)."
    ),
    remark_compat: bool | None = typer.Option(
        None,
        "--remark-compat/--no-remark-compat",
        help="Normalize legacy Remark syntax.",
    ),
    partial: list[str] = typer.Option(
        None, "--partial", help="Replace the partials search dirs (repeatable)."
    ),
    max_include_depth: int | None = typer.Option(
        None, "--max-include-depth", help="Max nested-include depth."
    ),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Serve a live, reloading preview that rebuilds on source changes."""
    from .serve import LiveReloadServer, watch_paths

    overrides = {
        "renderer": renderer,
        "theme": theme,
        "asset_base": asset_base,
        **_assembly_overrides(remark_compat, partial, max_include_depth, aspect),
    }
    try:
        resolved = resolve_source(
            source, config_override=config, cli_overrides=overrides
        )
        # Surface a config/render error immediately rather than after the server
        # is up (the running server then shows build errors as an overlay).
        get_renderer(resolved.config.renderer)
    except LecternError as e:
        raise _fail(e) from None

    serve_cfg = resolved.config.serve
    server = LiveReloadServer(
        source,
        out_dir=resolved.out_dir,
        host=host or serve_cfg.host,
        port=port or serve_cfg.port,
        coi=serve_cfg.coi if coi is None else coi,
        open_browser=serve_cfg.open if open_browser is None else open_browser,
        browser=browser or serve_cfg.browser,
        config_override=config,
        cli_overrides=overrides,
        watch=watch_paths(resolved),
    )
    server.run()


@app.command(name="config")
def config_cmd(
    source: Path = typer.Argument(
        ..., metavar="SOURCE", help="Manifest, deck dir, or .md file."
    ),
    renderer: str | None = typer.Option(None, "-r", "--renderer"),
    theme: str | None = typer.Option(None, "-t", "--theme"),
    asset_base: str | None = typer.Option(None, "--asset-base"),
    aspect: str | None = typer.Option(None, "--aspect"),
    remark_compat: bool | None = typer.Option(
        None, "--remark-compat/--no-remark-compat"
    ),
    partial: list[str] = typer.Option(
        None, "--partial", help="Replace the partials search dirs (repeatable)."
    ),
    max_include_depth: int | None = typer.Option(None, "--max-include-depth"),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Show the effective merged config and where each value came from."""
    overrides = {
        "renderer": renderer,
        "theme": theme,
        "asset_base": asset_base,
        **_assembly_overrides(remark_compat, partial, max_include_depth, aspect),
    }
    try:
        resolved = resolve_source(
            source, config_override=config, cli_overrides=overrides
        )
    except LecternError as e:
        raise _fail(e) from None

    cfg = resolved.config
    ucp = resolved.user_config_path
    user_state = "present" if (ucp and ucp.is_file()) else "absent"
    manifest = "(none)" if resolved.mode == "single" else resolved.origin_display

    typer.secho(f"lectern config — {source}", bold=True)
    typer.echo(f"  mode:        {resolved.mode}")
    typer.echo(f"  deck root:   {resolved.root}")
    typer.echo(f"  manifest:    {manifest}")
    typer.echo(f"  user config: {ucp} ({user_state})")
    typer.echo("")
    typer.secho("config  (value · source layer)", bold=True)

    dump = cfg.model_dump()
    for key, value in dump.items():
        if key == "slides":
            continue
        if key in _SECTION_KEYS and isinstance(value, dict):
            for sub, subval in value.items():
                origin = _leaf_origin([key, sub], resolved.layers)
                _emit_kv(f"[{key}] {sub}", subval, origin)
        else:
            _emit_kv(key, value, _leaf_origin([key], resolved.layers))

    typer.echo("")
    typer.secho("resolved paths", bold=True)
    typer.echo(f"  out_dir:     {resolved.out_dir}")
    typer.echo(f"  build_dir:   {resolved.build_dir}")
    typer.echo(f"  partials:    {[str(p) for p in resolved.partial_dirs]}")
    typer.echo(f"  theme_paths: {[str(p) for p in resolved.theme_dirs]}")
    typer.echo(f"  slides:      {len(resolved.entries)} entr(ies) [{resolved.mode}]")


def _emit_kv(label: str, value: object, origin: str) -> None:
    rendered = json.dumps(value)
    dim = origin == "default"
    line = f"  {label:<22} = {rendered}"
    typer.echo(line, nl=False)
    typer.secho(f"   ({origin})", fg=(typer.colors.BRIGHT_BLACK if dim else None))


def _clean_protected(resolved) -> set[Path]:
    """Directories `clean` must never remove: the deck root, partials/theme
    search dirs, a local ``asset_base``, the theme file's dir, and every dir that
    holds a source slide. Used to keep `clean` to disposable output only."""
    root = resolved.root
    prot = {root, *resolved.partial_dirs, *resolved.theme_dirs}
    for entry in resolved.entries:
        prot.add((root / entry.split("#", 1)[0]).parent)
    ab = resolved.config.asset_base
    if ab and "://" not in ab:
        p = Path(ab).expanduser()
        prot.add(p if p.is_absolute() else root / p)
    theme = resolved.config.theme
    if theme and theme.endswith(".css"):
        p = Path(theme).expanduser()
        prot.add((p if p.is_absolute() else root / p).parent)
    return {p.resolve() for p in prot}


def _clean_unsafe(candidate: Path, resolved) -> str | None:
    """Why ``candidate`` must NOT be removed, or ``None`` if it's safe — a
    disposable directory strictly inside the deck root that holds no source."""
    root = resolved.root.resolve()
    c = candidate.resolve()
    if c == root:
        return "is the deck root"
    if root not in c.parents:
        return "is outside the deck root"
    protected = _clean_protected(resolved)
    if c in protected:
        return "is a deck source/input directory"
    if any(c in p.parents for p in protected):
        return "contains deck source files"
    return None


@app.command(name="clean")
def clean_cmd(
    source: Path = typer.Argument(
        Path("."),
        metavar="[SOURCE]",
        help="Deck dir, manifest, or .md file (default: current dir).",
    ),
    remove_cache: bool = typer.Option(
        False,
        "--all",
        "--cache",
        help="Also remove the build dir (the cached PDF master).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List what would be removed; delete nothing."
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip the confirmation prompt."
    ),
    config: Path | None = typer.Option(
        None, "--config", help="Override the deck manifest (.toml)."
    ),
) -> None:
    """Remove a deck's generated output (the out_dir; also the build_dir with --all).

    Only ever removes the deck's configured, deck-root-relative ``out_dir`` /
    ``build_dir`` — never a source, partials, theme, or asset directory.
    """
    try:
        resolved = resolve_source(source, config_override=config)
    except LecternError as e:
        raise _fail(e) from None

    candidates = [("out_dir", resolved.out_dir)]
    if remove_cache:
        candidates.append(("build_dir", resolved.build_dir))

    targets: list[tuple[str, Path]] = []
    for label, path in candidates:
        reason = _clean_unsafe(path, resolved)
        if reason is not None:
            typer.secho(
                f"  skip {label} ({path}) — {reason}",
                fg=typer.colors.YELLOW,
                err=True,
            )
        elif not path.exists():
            typer.echo(f"  {label}: {path} — nothing to remove")
        else:
            targets.append((label, path))

    if not targets:
        typer.secho("nothing to clean.", fg=typer.colors.GREEN)
        return

    typer.secho("would remove:" if dry_run else "to remove:", bold=True)
    for label, path in targets:
        typer.echo(f"  {label}: {path}")
    if dry_run:
        return
    if not yes:
        typer.confirm("proceed?", abort=True)

    import shutil

    for _label, path in targets:
        shutil.rmtree(path)
        typer.secho(f"  removed {path}", fg=typer.colors.GREEN)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"lectern {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    pass


if __name__ == "__main__":
    app()

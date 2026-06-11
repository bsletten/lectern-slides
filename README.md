# Lectern

[![CI](https://github.com/bsletten/lectern-slides/actions/workflows/ci.yml/badge.svg)](https://github.com/bsletten/lectern-slides/actions/workflows/ci.yml)

**Lectern** is a Python CLI that assembles Markdown slide sources — transclusion,
`#1-3` slide ranges, partial search paths — into one deck and renders it via
reveal.js (with remark / marp / quarto as alternates), with a live-reload preview
server and vector PDF export. It's the Markdown front-end to a larger
resource-oriented slide system; the `Source` seam is designed so a semantic-CMS
backend can replace the filesystem later.

Jump to **[Install](#install)** and **[Usage](#usage)** to get going.

## Names (locked)

- **Product / tool:** Lectern
- **CLI command:** `lectern`
- **PyPI distribution + GitHub repo:** `lectern-slides` → `pip install lectern-slides`
- **Python import package:** `lectern`
- **PDF extra:** `lectern-slides[pdf]`
- **License:** MIT (see `LICENSE`); all dependencies are permissive (MIT/BSD/Apache)

## Install

```bash
pip install lectern-slides            # core: assemble + reveal/remark HTML + watch

# PDF export (vector master, imposition, B&W) — pulls Playwright, pypdf, reportlab:
pip install 'lectern-slides[pdf]'
playwright install chromium           # one-time: the headless browser for PDF

# Optional external tools, only for their adapters (each is availability-guarded):
#   marp-cli (npm i -g @marp-team/marp-cli)  → marp adapter: html / pdf / pptx
#   quarto   (quarto.org)                    → quarto adapter: high-quality html
#   ghostscript (brew install ghostscript)   → full-document B&W engine
```

## Usage

`SOURCE` is a **deck directory** (containing `deck.toml`/`lectern.toml`, else
directory order), a **`.toml` manifest**, or a single **`.md` file**.

```bash
# Assemble: expand includes / #1-3 ranges / partials into one Markdown deck
lectern assemble ./talks/ai-sec -o assembled.md     # omit -o to write to stdout

# Check: validate includes/ranges/partials (and surface warnings), no render
lectern check ./talks/ai-sec

# Config: show the effective merged config and where each value came from
lectern config ./talks/ai-sec

# Build: render to the deck's out_dir (default: reveal HTML)
lectern build ./talks/ai-sec                         # -> dist/index.html
lectern build ./talks/ai-sec -t ./themes/mine.css -o site

# Live preview: rebuilds on change with SSE reload + build-error overlay
lectern watch ./talks/ai-sec                         # serves http://127.0.0.1:8080
```

### Configuration

A deck is **external** to this tool. `SOURCE`'s directory (the manifest's folder)
is the **deck root**, resolved to an absolute path, and **every relative path in
the config — `slides`, `partials`, `asset_base`, `theme`, `out_dir`, `build_dir`
— resolves against it**, never your CWD or where Lectern is installed. Absolute
paths and `~` pass through; URLs pass through. So `out_dir`/`build_dir` default to
`dist`/`build` *inside the deck's own repo*.

Config is merged from three layers, **highest precedence first**, over the
built-in defaults:

1. **CLI flags** — `--theme`, `--renderer`, `--asset-base`, `--aspect`, `--out`,
   `--remark-compat`, `--partial` (repeatable), `--max-include-depth`, the PDF
   flags, …
2. the deck's **`deck.toml`** (or `lectern.toml`),
3. a **user config** at `$XDG_CONFIG_HOME/lectern/config.toml` (fallback
   `~/.config/lectern/config.toml`).

The merge is a deep, per-key merge, so a user config can set a house theme and a
shared partials library once and every separate deck repo inherits them (use
absolute/`~` paths there, since relative paths resolve against each deck's root):

```toml
# ~/.config/lectern/config.toml
theme    = "house"                # a bundled name, or an absolute/~ path
partials = ["~/talks/_lib"]
```

Inspect the effective, merged config and **where each value came from** with:

```bash
lectern config ./talks/ai-sec                 # value · (cli | deck.toml | user | default)
lectern config ./talks/ai-sec --theme grove   # preview an override before building
```

The full key reference (top-level + `[serve]`/`[reveal]`/`[marp]`/`[quarto]`/`[pdf]`)
is in `SPECIFICATION.md`. Note: not every key has a flag — `partials`,
`remark_compat`, `max_include_depth`, and `aspect` are exposed on
`build`/`watch`/`assemble`/`check`; the rest are config-only.

### Themes

`theme =` is either a **bundled name** or a **path**:

- **bundled name** (e.g. `theme = "base"`, `"cartesian"`, `"grove"`,
  `"soft-editorial"`) → the CSS shipped inside the package at
  **`src/lectern/themes/<name>.css`**. This is the home for **reusable themes**:
  drop a `.css` there and it's available by name to every deck on every machine
  that installs Lectern. (The top-level `themes/` directory and the sample deck's
  `themes/` are *not* search paths — the former is unshipped design source, the
  latter is deck-local to the sample.)
- **path** (`./themes/mine.css`, `~/talks/house.css`, or absolute) → loaded
  directly; a relative path resolves against the deck root. Use this for a
  one-off deck theme, or a personal theme shared across decks via an absolute/`~`
  path (or set once in your user config).

Themes are CSS driven by design tokens (`--bg`, `--accent`, `--font-display`, the
size scale, …) and the Remark-parity classes; the structural layout layer
(`.slide` anchor grid, `.place` boxes) is theme-independent, so a theme swap never
moves content.

### Renderers (`-r/--renderer`, or `renderer =` in the manifest)

| Renderer | Engine | Formats |
| --- | --- | --- |
| `reveal` *(default)* | native reveal.js | `html`, `pdf` |
| `remark` | native remark.js (legacy-deck parity) | `html` |
| `marp` | shells out to `marp-cli` | `html`, `pdf`, `pptx` |
| `quarto` | shells out to `quarto render` | `html` |

The format is gated by the adapter's capabilities; asking for one it can't make
prints a hint toward an adapter that can (e.g. `-f pptx` → *try renderer: marp*).

### PDF export (`-f pdf`)

```bash
lectern build ./talks/ai-sec -f pdf                  # 2up-notes handout (default)
lectern build ./talks/ai-sec -f pdf --layout 1up     # clean projection slides
lectern build ./talks/ai-sec -f pdf --ink-saver --paper letter
```

A single **vector master** is printed once (headless Chromium) and then imposed;
re-exporting another layout/color reuses the cached master.

| Flag | Effect |
| --- | --- |
| `--layout` | `1up`, `2up`, `2up-notes`, `4up`, `6up`, `3up-notes` |
| `--paper` | `deck`, `letter`, `a4`, or `WxH` (multi-up defaults to `letter`) |
| `--bw` | grayscale (vector `tokens` engine; `ghostscript` for raster too) |
| `--no-backgrounds` | drop background fills/images for clean paper |
| `--light-inverse` | flip dark slides to light for ink economy |
| `--ink-saver` | `--bw` + `--no-backgrounds` + `--light-inverse` |

All knobs also live under `[pdf]` in the manifest (CLI flags win). See
`PDF-EXPORT.md` for the full set and `SPECIFICATION.md` for the source format and
config reference. Run `lectern --help` (or `lectern build --help`) for everything.

## What's here

```
src/lectern/       ← the implementation: assemble · render adapters · pdf · serve · theming
src/lectern/themes/     ← bundled themes (base, cartesian, grove, soft-editorial); add one here to ship it by name
tests/             ← unit + golden-file + render/PDF tests
SPECIFICATION.md   ← the full functional + technical spec (the substance)
PDF-EXPORT.md      ← the PDF strategy (vector master → 2-up-with-notes, B&W, posters)
CLAUDE.md          ← the operating manual: build order, conventions, milestones
ROADMAP.md         ← phases: assemble → render/watch → adapters → components → CMS
deck.toml          ← a minimal starter manifest (root example)
examples/sample-deck/   ← a complete reference deck that exercises every feature
    deck.toml · slides/ · _partials/ · assets/ · themes/ (japandi · midnight · paper)
    README.md           ← how the sample maps to features
    japandi-preview.html ← static preview of the Japandi theme (open in a browser)
```

## Development

```bash
uv sync --extra pdf                              # runtime + dev + PDF deps
uv run pytest                                    # unit + golden + render/PDF tests
uv run ruff check . && uv run ruff format --check .
```

The PDF/render tests that need a browser are skipped unless Chromium is present
(`uv run playwright install chromium` to enable them). Lectern was built milestone
by milestone (M1 assemble → M6 PDF finishing); `CLAUDE.md` is the operating manual
and remains the guide for further work with Claude Code, and `ROADMAP.md` covers
what's beyond v1 (component embeds, then a graph/CMS `Source` backend).

## Design decisions

- Default renderer: **reveal** (native, no external binary); **remark** is the
  legacy-parity adapter; **marp**/**quarto** are opt-in subprocess adapters,
  availability-guarded. No mandatory Pandoc.
- Source directives live in **HTML comments** so raw `.md` stays valid CommonMark.
- Core stays dependency-light; **Playwright + pypdf + reportlab** are the
  `lectern-slides[pdf]` extra, imported lazily.
- Manifests are **TOML**; the PDF default is **2up-notes** (one vector master,
  imposed two-up with the real speaker notes beside each slide).
- The `Source` protocol, adapter registry, theme token contract, and `[serve].coi`
  headers are seams kept clean so later phases (components, CMS backend) stay cheap.

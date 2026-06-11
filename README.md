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

# Build: render to the deck's out_dir (default: reveal HTML)
lectern build ./talks/ai-sec                         # -> dist/index.html
lectern build ./talks/ai-sec -t ./themes/mine.css -o site

# Live preview: rebuilds on change with SSE reload + build-error overlay
lectern watch ./talks/ai-sec                         # serves http://127.0.0.1:8080
```

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
tests/             ← unit + golden-file + render/PDF tests
SPECIFICATION.md   ← the full functional + technical spec (the substance)
PDF-EXPORT.md      ← the PDF strategy (vector master → 2-up-with-notes, B&W, posters)
CLAUDE.md          ← the operating manual: build order, conventions, milestones
ROADMAP.md         ← phases: assemble → render/watch → adapters → components → CMS
deck.toml          ← a minimal starter manifest (root example)
themes/base.css    ← the token contract + Remark-parity classes
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

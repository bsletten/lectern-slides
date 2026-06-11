# Lectern — design package

[![CI](https://github.com/bsletten/lectern-slides/actions/workflows/ci.yml/badge.svg)](https://github.com/bsletten/lectern-slides/actions/workflows/ci.yml)

Specifications and starter assets for building **Lectern**, a Python tool that
assembles Markdown slide sources into a deck and renders it via reveal.js (with
remark / marp / quarto as alternates), with live preview and PDF export. This is
the Markdown front-end to a larger resource-oriented slide system; the `Source`
seam is designed so a semantic-CMS backend can replace the filesystem later.

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
CLAUDE.md          ← Claude Code reads this first: build order, conventions, milestones
SPECIFICATION.md   ← the full functional + technical spec (the substance)
PDF-EXPORT.md      ← the PDF strategy (vector master → 2-up-with-notes, B&W, posters)
ROADMAP.md         ← phases: assemble → render/watch → adapters → components → CMS
deck.toml          ← a minimal starter manifest (root example)
themes/base.css    ← the token contract + Remark-parity classes
examples/sample-deck/   ← a complete reference deck that exercises every feature
    deck.toml · slides/ · _partials/ · assets/ · themes/ (japandi · midnight · paper)
    README.md           ← how the sample maps to features
    japandi-preview.html ← static preview of the Japandi theme (open in a browser)
```

## How to build it with Claude Code

1. Unzip — it expands to a `lectern-slides/` folder. That's your project root and
   git repo (`cd lectern-slides && git init`).
2. Open the directory in Claude Code (Code tab in the desktop app, `claude` in a
   terminal, or the VS Code / JetBrains extension). It will pick up `CLAUDE.md`.
3. Give it the first milestone. A good opening prompt:

   > Read CLAUDE.md, SPECIFICATION.md, and PDF-EXPORT.md, then implement
   > **Milestone M1 (assemble)** only: the range parser, fence-aware slide
   > splitter, include resolver with partial search paths and cycle/depth guards,
   > frontmatter handling, and the `lectern assemble` / `lectern check` commands,
   > with unit + golden-file tests. Add a fixtures deck. Stop and run pytest
   > before moving on.

4. Proceed milestone by milestone (M1 → M6 in CLAUDE.md), running tests and
   committing after each. Point it at `examples/sample-deck` once M2 (reveal
   render) exists — that's the acceptance fixture.

## Decisions already made (so Claude Code doesn't re-litigate)

- Default renderer: **reveal** (confirmed). remark ships as the legacy adapter.
- Source directives live in **HTML comments** so raw `.md` stays valid CommonMark.
- Core stays dependency-light; **Playwright + pypdf** are a `lectern-slides[pdf]` extra;
  marp/quarto are opt-in subprocess adapters; no mandatory Pandoc.
- PDF default layout: **2up-notes** (vector master, imposed two-up with notes).

## Still open (confirm when you like)

- `2up-notes` geometry: notes **beside** vs **below** each slide.
- Manifest format TOML (recommended) vs YAML.
- Whether to bundle the remark legacy adapter on day one (recommended: yes).

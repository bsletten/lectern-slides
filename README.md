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

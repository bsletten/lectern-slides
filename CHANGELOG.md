# Changelog

All notable changes to **lectern-slides** are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
aims to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-06-17

First public release. A dependency-light Python CLI (`lectern`) that assembles
Markdown slide sources into one deck and renders it through a pluggable framework
adapter, with a live-reload preview server and vector PDF export.

### Assembly

- Transclusion and slide-range includes with the `#1-3,14` range grammar.
- Fence-aware slide splitter; relative + `partials` search-path resolution with
  cycle and depth guards.
- Frontmatter handling and a source-map so every diagnostic cites the
  originating `file:line`/directive, never an internal offset.
- `lectern assemble` and `lectern check` (validation + warnings, no render).

### Rendering

- Pluggable adapter registry: **reveal** (default) and **remark** native
  adapters (Python + Jinja2 only), plus **marp** and **quarto** subprocess
  adapters that `available()`-guard their external binary.
- Remark input-compat normalizer so existing Remark decks assemble and render
  unchanged.
- Neutral directive syntax in HTML comments / Pandoc fenced divs: per-slide
  classes/id/data-attributes, inline and block classes, content anchors, placed
  boxes, and incremental builds.
- Theme resolution with a token contract; ships a `base.css` plus a set of
  swappable themes. A deck's own theme folder is discovered automatically.
- Asset resolver (directory + URL `asset_base`): copies, content-hashes, and
  rewrites references; garbage-collects orphaned hashed assets.
- Mermaid diagrams, Font Awesome icons, image sizing, and raw HTML/`<canvas>`
  passthrough.

### Speaker notes

- `<!-- notes -->` comment blocks and `::: {.notes}` fenced divs route to the
  presenter view.
- `notes:presenter` category for notes that show in the presenter view but are
  **excluded from the printed PDF handout**; a mistyped category is flagged.

### Watch + serve

- `lectern watch` — Starlette/Uvicorn serving `dist/`, `watchfiles` rebuild, SSE
  live-reload, and a build-error overlay.
- `[serve].coi` COOP/COEP headers (the on-ramp for WASM-threads / WebGPU embeds).

### PDF export

- Vector master printed once via headless Chromium, then imposed and cached for
  reuse across layout/color changes.
- Layouts `1up`, `2up`, `2up-notes`, `4up`/`2x2`, `6up`, `3up-notes`; paper
  presets and `WxH`; B&W (token and ghostscript engines), `--no-backgrounds`,
  `--light-inverse`, and `--ink-saver`.
- `-f pdf|pptx` output across capable adapters with graceful degradation.

### Accessibility

- `lectern check` runs a source-cited a11y audit by default: accessible-name and
  alt-text checks, heading-order and contrast lint, tagged PDF output, a document
  outline, and forced-colors support.

[Unreleased]: https://github.com/bsletten/lectern-slides/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/bsletten/lectern-slides/releases/tag/v0.1.0

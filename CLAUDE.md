# CLAUDE.md — Lectern

Guidance for building Lectern with Claude Code. Read `SPECIFICATION.md` for the
full design and `ROADMAP.md` for sequencing. This file is the operating manual.

## What you are building

A Python CLI (`lectern`) that assembles Markdown slide sources (transclusion +
slide-range includes) into one deck and renders it via a pluggable framework
adapter, with a live `--watch` preview server. It is the Markdown front-end to a
larger resource-oriented slide system; keep the `Source` seam clean so a future
CMS/graph backend can replace the filesystem source without changing anything
downstream.

## Prime directives

- **Build the smallest thing that works, then grow.** Follow the milestones below
  in order. Do not scaffold future phases speculatively.
- **Keep the core dependency-light.** `reveal` and `remark` adapters use only
  Python + templates. `marp`/`quarto` adapters shell out and must `available()`-
  guard the external binary. Never make Pandoc a required dependency.
- **Directives live in HTML comments** so raw `.md` stays valid CommonMark. The
  assemble stage expands them.
- **Pure where it matters.** `ranges.py`, the fence-aware splitter, and the
  include resolver are pure functions with no I/O — they get the heaviest tests.
- **Errors map to source.** Carry a source-map; every user-facing error cites the
  originating `file:line`/directive, never an internal offset.
- **Static-mostly.** Do not model animation timelines. Raw HTML/script passthrough
  plus the asset pipeline is the entire animation story for now.

## Tech choices (don't re-litigate)

Python ≥3.11 · `typer` CLI · `pydantic` config · `jinja2` templates ·
`python-frontmatter` · `watchfiles` · `starlette`+`uvicorn` server · `httpx` for
URL assets · `tomllib` (stdlib). Package with hatchling: distribution name
**`lectern-slides`** (PyPI/GitHub), import package `lectern`, `console_scripts` →
`lectern`, PDF extra `lectern-slides[pdf]`, license **MIT** (`LICENSE` file +
`license = "MIT"` in pyproject). (Import name `lectern` technically
shares PyPI's Minecraft `lectern` namespace; harmless here — namespace to
`lectern_slides` only if that ever matters.) Format with `ruff format`; lint with
`ruff`; type-check with `pyright`/`mypy`.

## Milestones (each ends in a working, committed, tested state)

**M1 — assemble.** `ranges.py` (the `#1-3,14` grammar), fence-aware slide
splitter, include resolver (relative + `partials` search paths + cycle/depth
guards), frontmatter handling, source-map. `lectern assemble SOURCE -o out.md`
and `lectern check SOURCE`. Unit + golden-file tests. No rendering yet.

**M2 — render (reveal).** Config model, theme resolution + token injection,
`reveal` adapter via Jinja2 template (assembled md → reveal.js HTML), asset
resolver (dir + URL, copy + rewrite). `lectern build SOURCE`. Ship `themes/base.css`.

**M3 — watch + serve.** Starlette/Uvicorn serving `dist/`, `watchfiles` rebuild,
SSE live-reload, build-error overlay, `[serve].coi` COOP/COEP headers.
`lectern watch SOURCE`.

**M4 — remark adapter + migration.** Native `remark` adapter and the Remark
input-compat normalizer (`.cls[]`, `class:`/`name:`/`layout:` property lines,
`--` flatten) so existing decks assemble and render unchanged.

**M5 — marp + quarto adapters.** Subprocess adapters with neutral→flavor lowering
and `available()` guards; capability-based graceful degradation. `-f pdf|pptx`.

**M6 — PDF finishing.** Per `PDF-EXPORT.md`: the 1-up vector master via Playwright
ships earlier (M2); this milestone adds N-up imposition / `3up-notes` (pypdf +
reportlab overlay),
the B&W engines, `light_inverse`, auto poster capture, and handout chrome.

Stop here for v1. Phases beyond (components/WASM/WebGPU, CMS source backend) are
in `ROADMAP.md` and are *not* M-scope.

## Working habits

- Run `pytest` before declaring any milestone done; commit per milestone with a
  short message.
- When you touch `ranges.py`, the splitter, or the include resolver, add/adjust
  tests in the same change — these are the load-bearing pure functions.
- Add a `fixtures/` deck early (M1) that exercises includes, ranges, partials,
  assets, classes, notes, and a raw-HTML/`<canvas>` slide; grow it as you go.
- Prefer one clear way to do a thing over configurable cleverness. This is one
  author's tool.

## Seams to respect (so later phases are cheap, without building them now)

- `source.py` `Source` protocol — filesystem now, CMS/graph later. Nothing
  downstream may import filesystem paths directly; go through `Source`.
- `render/base.py` registry — adapters are discovered, not hard-wired.
- Theme **token contract** — components and adapters read tokens, never hardcode
  colors/sizes.
- `[serve].coi` headers — the on-ramp for WASM-threads/WebGPU embeds.

## Definition of done (v1)

`lectern watch ./talks/ai-sec` serves a live, reloading reveal deck assembled
from a manifest with at least one ranged partial include and a URL `asset_base`;
`lectern build -f pdf` produces a vector PDF; existing Remark decks render via the
`remark` adapter unchanged; `pytest` is green.

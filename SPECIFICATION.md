# Lectern — Specification

> Product/tool name: **Lectern**. CLI command: `lectern`. PyPI distribution and
> GitHub repo: **lectern-slides** (`pip install lectern-slides`). Import package:
> `lectern`. "Lectern"
> = the thing that holds your talk.

## 0. What this is, and what it is not

Lectern is a Python tool that **assembles** Markdown slide sources from a
directory — resolving transclusions and slide-range includes — into a single
deck, then **renders** that deck through a pluggable framework adapter
(reveal.js by default; remark, marp, quarto optional). It serves a live,
reloading preview in `--watch` mode. Assets resolve from a local base directory
or a URL.

This is deliberately the **Markdown production front-end** to the larger
resource-oriented slide system you've been designing, in which slides are one
*projection* of a knowledge graph and Markdown is the linear, "degenerate"
authoring on-ramp. Lectern must therefore keep a clean `Source` seam so a future
CMS/graph backend can replace the filesystem source **without touching** the
preprocess, render, or serve layers.

**Non-goals for v1** (explicit, to protect scope):
- The knowledge-graph / resolution engine itself. Lectern feeds it later; it is not it.
- Animation timelines and choreography (state, duration, interaction). Simple
  CSS/JS-in-fragment animation is fine; orchestrated timelines are deferred.
- Competing with Slidev on polish or Quarto on output quality for general users.
- Multi-user, auth, plugin marketplace, or any "platform" surface.

## 1. Design principles (carried from prior architecture decisions)

1. **Your tool, not a platform.** Clean internals so others *could* use it, but
   every decision optimizes for one author. No flexibility tax paid up front.
2. **Static-mostly for a long time.** Don't model animation choreography. Leave
   a seam (raw HTML/script + asset/component pipeline) and stop there.
3. **Lightweight core, heavy renderers opt-in.** No mandatory Pandoc dependency.
   Marp and Quarto are subprocess adapters invoked only when selected.
4. **Standard-Markdown-compatible source.** All Lectern-specific directives live
   inside HTML comments, so raw `.md` files still render correctly in GitHub,
   editors, and any CommonMark viewer.
5. **Addressable later.** A `Source` abstraction plus provenance source-maps mean
   today's files can become tomorrow's graph nodes without a rewrite.

## 2. Source format — "Lectern Markdown"

Base is **CommonMark**. On top of it:

| Concern | Syntax | Notes |
|---|---|---|
| Slide break | a line that is exactly `---` | fence-aware: ignored inside ``` / ~~~ code |
| Per-slide attributes | `<!-- slide: .center .middle .inverse #intro data-x=1 -->` at slide top | classes / id / data; adapters translate |
| Slide accessible name | `<!-- slide: label="…" -->` (or `aria-label="…"`) | the slide's name for screen readers; `label` is lowered to `aria-label` on the reveal `<section>`. Give heading-less image/quotation slides a `label` — `lectern check` flags slides with neither a heading nor a label. |
| Speaker notes | `<!-- notes -->` … `<!-- /notes -->` | adapters map to reveal `aside.notes`, marp comments, quarto `::: notes` |
| Inline span class | `[text]{.cls}` (Pandoc-style) | neutral; reveal/remark lower to framework form |
| Block class | `::: {.cls}` … `:::` (Pandoc fenced div) | neutral |
| Slide content anchor | `<!-- slide: .top\|.middle\|.bottom .left\|.center\|.right -->` | nine-point grid; positions the whole content block |
| Placed box | `::: {.place .top .right}` … `:::` (or `style="left:..;top:.."`) | absolutely anchored box; any number per slide |
| Incremental build | `::: incremental` … `:::` around a list | recognized block class; reveal adapter lowers each child to `.fragment` |
| Raw HTML | allowed | for `<canvas>`, `<script type="module">`, embeds; live embeds resolve to a poster frame in PDF (see `PDF-EXPORT.md`) |
| Include / transclude | `<!-- include: PATH -->` / `<!-- include: PATH#RANGES -->` | see §3 |

Rationale for the comment-directive choice: it satisfies "still support markdown
parsers" exactly — vanilla parsers drop the comments, and the **assemble stage**
(which you explicitly OK'd) expands them. We do not invent a custom inline token
that would render as literal text in a plain viewer.

> Migration note: existing decks use Remark's `.cls[content]`, `class:` property
> lines, and `--` increments. Ship a `remark` *input-compat* mode (a thin
> normalizer) so current decks assemble unchanged; new content uses the neutral
> forms above. (The earlier `remark2html` converter is a reference for the
> `.cls[]` and property-line transforms.)

## 3. Includes, partials, and slide ranges (the core ask)

Directive (HTML comment, parser-safe):

```
<!-- include: partials/rdf-intro.md -->          whole file (all its slides)
<!-- include: partials/rdf-intro.md#1-3,14 -->   selected slides only
```

**PATH resolution order:** (1) relative to the including file's directory; (2)
each configured `partials` search dir, in order; (3) otherwise error, citing the
directive's source location.

**RANGES grammar** — 1-indexed slides within the included file, where slides are
delimited by `---` (fence-aware):
- `N` — single slide
- `A-B` — inclusive range
- `A-` — slide A through end
- `-B` — start through slide B
- comma-separated list, whitespace ignored: `#1-3,14`, `#2`, `#5-`
- out-of-range index → error with the file path and its available slide count.

**Semantics:**
- Nested includes allowed (a partial may include partials). Detect cycles via a
  (path, range) stack; enforce `max_include_depth` (default 16).
- A partial's own YAML frontmatter is ignored for slide content in v1 (warn if
  non-empty). Config comes from the deck manifest, not partials.
- The assembled file preserves `---` separators and prepends a provenance comment
  to each contributed slide: `<!-- @from partials/rdf-intro.md slide=2 -->`. The
  source-map drives error mapping; provenance comments are stripped before
  handing to renderers that would display them.

## 4. Deck definition: manifest vs directory mode

**Manifest mode (recommended).** A `deck.toml` (or `lectern.toml`) defines the
deck: an ordered `slides` list plus config. Explicit order, explicit config.

**Directory mode.** Point at a directory with no `slides` list; `.md` files are
included in lexical filename order. Recommend zero-padded numeric prefixes
(`010-intro.md`, `020-rdf.md`). A `deck.toml` may still supply config without
enumerating slides.

**Entry resolution.** The CLI `SOURCE` argument may be: a manifest file; a deck
directory (looks for `deck.toml`/`lectern.toml`, else directory mode); or a
single `.md` file.

## 5. Configuration schema (TOML, validated with pydantic)

```toml
title       = "The Security of AI Systems"
author      = "Brian Sletten"
renderer    = "reveal"          # reveal | remark | marp | quarto
theme       = "base"            # bundled name, or a path: "./themes/mine.css"
aspect      = "16:9"            # "16:9" | "4:3" | "1280x720"
asset_base  = "/abs/or/url"     # local dir OR URL (e.g. the semantic CMS)
partials    = ["../partials", "~/talks/_lib"]   # search dirs, in order
out_dir     = "dist"
build_dir   = "build"

# Ordered deck contents. Each entry is a path with optional #ranges,
# OR a literal include directive. Omit `slides` to use directory mode.
slides = [
  "00-title.md",
  "rdf-intro.md#1-3,14",        # range include resolved via `partials`
  "10-threat-model.md",
]

[serve]
host = "127.0.0.1"
port = 8080
open = true
coi  = false   # set cross-origin-isolation headers (COOP/COEP) for WASM/WebGPU

[reveal]
controls   = true
progress   = true
transition = "none"
highlight  = true      # load the highlight plugin; the theme supplies token colors
math       = "katex"   # "katex" | "mathjax" | false — typeset $…$ / $$…$$

[marp]
# passthrough flags for marp-cli

[quarto]
# passthrough for quarto render
```

## 6. Asset resolution

A reference is any image target, `src`, or `href`.

- `http(s)://…` → left as-is.
- root-absolute `/p` → joined with `asset_base`. If `asset_base` is a **dir**,
  the file is copied into `dist/assets/` (deduped by content hash) and the ref
  rewritten to a relative path. If a **URL**, the ref is prefixed.
- relative `p` → resolved against the *including file's* directory, copied into
  `dist/assets/`, rewritten relative.
- missing asset → warning (build continues) + a visible placeholder, with the
  originating slide cited.

CLI `--asset-base DIR|URL` overrides config. The CMS future is just
`asset_base = "https://cms.example/…"`.

## 7. Renderer adapters

Interface (one small protocol):

```python
class Renderer(Protocol):
    name: str
    def available(self) -> bool: ...                  # external bin present?
    def capabilities(self) -> Caps: ...               # {html, pdf, pptx, embeds}
    def render(self, deck: AssembledDeck, cfg: Config, out: Path) -> RenderResult: ...
```

- **`reveal` (default, native, no external binary).** Jinja2 template loads
  reveal.js (vendored locally, or CDN), feeds the assembled Markdown via reveal's
  Markdown plugin *or* pre-split `<section>`s, injects the theme CSS, and passes
  raw HTML/`<script type="module">` through untouched. This is the best target
  for the future WASM/WebGPU embeds, so it leads. Loads the **highlight** plugin
  (tokenizes fenced code; the theme's `.hljs-*` rules color it — do *not* ship a
  competing hljs stylesheet) and, when `math` is set, the **math** plugin (KaTeX
  or MathJax) for `$…$` / `$$…$$`.
- **`remark` (native).** Template + remark.js. Understands `.cls[]` and property
  lines, so existing decks render unchanged. The legacy/parity path.
- **`marp` (subprocess `marp-cli`).** Lower neutral directives → Marp Markdown;
  run marp-cli for html/pdf/pptx. `available()` checks for the binary.
- **`quarto` (subprocess `quarto`).** Lower → `.qmd`; `quarto render`. Heavy,
  high-quality, opt-in.

Adapters declare capabilities; neutral features they can't honor degrade with a
single warning, never a crash.

## 8. Dev server & watch (`lectern watch`)

- Build once, serve `dist/` over an ASGI app (Starlette + Uvicorn).
- Watch the source files, every `partials` dir, the active theme, and local
  assets (via `watchfiles`). On change, re-run assemble+render for the affected
  deck and push a reload.
- **Live reload:** inject a tiny SSE (`EventSource`) client into served HTML; the
  server broadcasts `reload` after a successful rebuild. Build errors render as
  an in-page overlay instead of crashing the server.
- **Cross-origin isolation seam:** `[serve].coi = true` (or `--coi`) sets
  `Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Embedder-Policy: require-corp`, enabling `SharedArrayBuffer`,
  WASM threads, and the WebGPU/WASM workloads you'll want later. Document the
  consequence: cross-origin assets then need `Cross-Origin-Resource-Policy`.
- v1 reload is a full page reload; fragment-level HMR is a later nicety.

## 9. Theming & stylesheets

- Themes are CSS files driven by **design tokens** (CSS custom properties).
  `theme = "base"` → bundled `themes/base.css`; `theme = "./x.css"` → custom.
- **Token contract** (relied on by adapters and future components):
  `--slide-w`, `--slide-h`, color tokens (`--bg`, `--fg`, `--accent`,
  `--muted`, `--inverse-bg`, `--inverse-fg`, `--code-bg`, `--code-fg`), type
  tokens (`--font-display`, `--font-body`, `--font-mono`, a size scale), spacing.
- `themes/base.css` ships 16:9 sizing, print `@page`, and **Remark-parity
  classes** (`center`, `middle`, `inverse`, `quotation`, `quotation-source`,
  `footnote`) so your current decks look right out of the gate.
- **Layout primitives are theme-independent.** The slide-anchor grid
  (`.top/.middle/.bottom × .left/.center/.right`) and `.place` box anchoring are
  *structural*, not aesthetic — every theme must behave identically. So the
  adapter injects a shared **layout layer** (the sizing + positioning classes,
  the canonical copy lives in `base.css`) **first**, then the selected theme on
  top. Themes therefore carry only colour, type, and character — they must not
  redefine positioning. (This also means a theme swap never moves content.)
- reveal also exposes layout helpers usable from `::: {.cls}` or raw HTML:
  `r-stack` (overlay/centre layers), `r-fit-text` (auto-size to fill),
  `r-stretch` (fill remaining space, e.g. an image). Pass-through; degrade
  elsewhere.
- reveal/remark inject theme CSS directly; marp/quarto wrap or pass it through
  their own theme mechanisms.

## 10. Project layout

```
pyproject.toml                 # hatchling; dist name "lectern-slides", license MIT, console_scripts: lectern
LICENSE                        # MIT
src/lectern/
  cli.py                       # typer app
  config.py                    # pydantic models; TOML load/merge/validate
  source.py                    # Source protocol; FilesystemSource (CmsSource later)
  preprocess.py                # assemble: includes, ranges, partials, frontmatter
  slides.py                    # fence-aware slide model + range selection
  ranges.py                    # the #1-3,14 grammar parser (pure, well-tested)
  assets.py                    # resolution + copy/rewrite
  theming.py                   # theme resolution + token injection
  render/
    base.py                    # Renderer protocol + registry
    reveal.py  remark.py  marp.py  quarto.py
  serve.py                     # ASGI server + watchfiles + SSE reload + COI
  templates/                   # Jinja2 (reveal.html.j2, remark.html.j2, reload.js.j2)
  themes/base.css
tests/
  fixtures/                    # decks exercising includes/ranges/assets/classes/notes/raw-html
  test_ranges.py test_preprocess.py test_assets.py test_render_*.py
```

`source.py` is the seam: `Source` exposes `list()`, `read(path)`, `resolve(ref)`.
`FilesystemSource` implements it now; a future `CmsSource` implements the same
protocol against the graph (fetch nodes/partials/assets by URI/query) and nothing
downstream changes.

## 11. Dependencies

Runtime: `typer`, `pydantic`, `jinja2`, `python-frontmatter`, `watchfiles`,
`starlette`, `uvicorn`, `httpx` (URL asset fetch). `tomllib` is stdlib (3.11+).
PDF export (the `lectern-slides[pdf]` extra): `playwright` (drives headless Chromium for
the vector master render and poster capture) and `pypdf` + `reportlab` (both
BSD-3-Clause; N-up imposition /
handouts). Optional external binaries: `marp-cli` (npm), `quarto`, and
`ghostscript` (only for full-document B&W). Target Python ≥ 3.11.
See `PDF-EXPORT.md` for the full export strategy.

## 12. CLI surface

```
lectern build   SOURCE [--renderer R] [--theme T] [--asset-base A]
                       [--out DIR] [--config FILE] [-f html|pdf|pptx]
                       # PDF (see PDF-EXPORT.md): [--layout 1up|2up|4up|6up|3up-notes]
                       # [--bw] [--no-backgrounds] [--light-inverse] [--ink-saver] [--paper a4]
lectern watch   SOURCE [--port N] [--host H] [--open/--no-open] [--coi]
lectern assemble SOURCE [-o build/deck.md]   # preprocess only — the "assemble
                                             # then feed any renderer" escape hatch
lectern check   SOURCE                       # validate includes/ranges/assets, no render
```

## 13. Error handling & provenance

Every assemble error maps to a source `file:line` via the source-map: unresolved
partial, bad range, include cycle, exceeded depth, missing asset. Messages name
the originating directive, not an internal offset.

## 14. Testing

- Unit: range parser (exhaustive grammar cases), fence-aware splitter, include
  resolver (relative + search-path + cycles + depth), asset resolver, neutral→adapter lowering.
- Golden-file: fixture decks → expected assembled `.md`; rendered HTML asserted on
  structure (sections, classes, ids), not pixels.

## 15. Open decisions (please confirm before Claude Code starts)

1. **Default renderer: `reveal` — CONFIRMED.** Best embed story for the future
   WASM/WebGPU work. `remark` still ships as the legacy/parity adapter (see #4).
2. **Manifest format:** TOML (recommended) vs YAML.
3. **Neutral notes/classes syntax:** confirm the HTML-comment + Pandoc-div
   approach in §2, or name a preference.
4. **Bundle the `remark` legacy adapter on day one?** Recommended yes — it lets
   you point Lectern at existing decks immediately and retire the manual
   DeckTape/print path.

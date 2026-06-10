# Sample deck — feature tour

A reference deck that exercises every core Lectern feature. It doubles as the
canonical test fixture and as living documentation of the source format.

## Run it

```
lectern watch examples/sample-deck          # live preview at http://127.0.0.1:8080
lectern build examples/sample-deck -f pdf    # vector PDF
```

## Switch themes (one line)

In `deck.toml`:

```toml
theme = "./themes/japandi.css"    # Japandi: shoji-paper greige, indigo, sumi ink, a vermilion seal
# theme = "./themes/midnight.css" # dark, geometric sans
# theme = "./themes/paper.css"    # light, editorial serif
```

…or override without editing: `lectern build examples/sample-deck --theme ./themes/paper.css`.
All three honor the same token contract and class names — including the
`.hljs-*` syntax palette — so the identical Markdown renders cleanly under any of
them. That's the whole point.

## What each slide demonstrates

| Slide | Feature |
| --- | --- |
| `00-title.md`         | Introduction slide (`.center .middle .inverse`) |
| `10-agenda.md`        | Agenda (ordered list) |
| `20-qualifications.md`| Speaker qualifications via **transclusion** of `_partials/qualifications.md` |
| `25-code.md`          | **Syntax highlighting** (fenced `python`, reveal highlight plugin + theme palette) |
| `30-background.md`    | **Full background image** (`data-background-image`) |
| `40-incremental.md`   | **Incremental builds** (`::: incremental`) + speaker notes |
| `45-layout.md`        | **Content placement** — nine-point slide anchors + `::: {.place …}` boxes |
| `50-animation.md`     | **Embedded D3.js animation** (isolated iframe → `assets/d3-bars.html`) |
| `60-table.md`         | **Tables** (Markdown pipe table, themed) |
| `70-math.md`          | **LaTeX** inline `$…$` and display `$$…$$` |
| `80-closing.md`       | Closing slide + the theme-switch hint |

## Design notes (decisions Claude Code should honor)

**Recognized fenced classes.** `::: incremental` makes each child a build step;
the reveal adapter lowers it to `.fragment`. `::: notes` (and the
`<!-- notes -->…<!-- /notes -->` form) become speaker notes. Both are special
cases of the neutral `::: {.cls}` block from the spec.

**Why D3 is embedded as an iframe, not inline `<script>`.** Markdown renderers
inject slide HTML via `innerHTML`, and browsers do **not** execute `<script>`
tags added that way — an inline D3 script would silently do nothing. An isolated
page (`assets/d3-bars.html`) runs normally, restarts cleanly on each view, and is
exactly the shape the Phase-3 WASM/WebGPU component pipeline will formalize. This
is the recommended pattern for any live visualization.

**Math plugin.** `[reveal].math = "katex"` in `deck.toml` tells the reveal adapter
to load the math plugin so `$…$` / `$$…$$` typeset. Without it they render as
literal text.

**Syntax highlighting.** `[reveal].highlight = true` loads reveal's highlight
plugin to *tokenize* fenced code; the **theme** supplies the colors via `.hljs-*`
rules. So the adapter must not also inject a stock highlight.js stylesheet — that
would fight the theme. All three sample themes ship a matching palette.

**Cross-origin isolation.** `[serve].coi` is left `false` here because
`d3-bars.html` loads D3 from a CDN. Turning COI on (for SharedArrayBuffer / WASM
threads / WebGPU later) requires every cross-origin asset to send the right
CORP/CORS headers — vendor D3 locally before flipping it on.

# PDF Export — Strategy

How Lectern turns a deck into PDF. Read alongside `SPECIFICATION.md` (§7 reveal
adapter) and `examples/sample-deck/`.

## Principle

One **vector master**, many cheap derivations.

```
                          render-time                 post-process
  assembled deck ──▶ [ Chromium print: reveal     ──▶ 1-up master.pdf
                       ?print-pdf, vector ]              │
                       • backgrounds on/off              ├─▶ impose ──▶ 2-up / N-up / notes
                       • light-inverse                   │     (pypdf places vector pages)
                       • poster frames for embeds        └─▶ grayscale ──▶ B&W
                       • fragments flatten/steps                (tokens or Ghostscript)
```

The master is always 1 slide / page, vector, full color. Everything the user
asks for — 2-up, handouts with notes, B&W, no-backgrounds — is either a flag that
changes the *master render* or a transform *applied to the master*. We never fall
back to rasterizing the deck (that was DeckTape's failure mode).

## Engines

- **Render + capture:** Playwright for Python driving headless Chromium. One
  dependency, no Node. Gives `page.pdf(...)` (vector, honors `@page`,
  `print_background`) and `page.screenshot(...)` for poster capture, plus
  `emulate_media(media="print", reduced_motion="reduce")`.
- **Imposition (N-up / handouts):** `pypdf` (BSD-3-Clause, pure Python) places the
  source *vector* pages scaled and translated into the grid via
  `PageObject.add_transformation(Transformation().scale(s).translate(x, y))` +
  `merge_page`. The handout chrome that pypdf can't draw — borders, slide numbers,
  header/footer, and the **notes text** — is rendered as a thin overlay with
  `reportlab` (BSD-3-Clause) and merged in. Both pure-Python and permissive, so the
  whole tool stays MIT-clean. No quality loss (slide pages remain vector).
- **Grayscale (optional, for full-document B&W incl. raster images):** Ghostscript
  (`-sColorConversionStrategy=Gray`). External binary; only needed for the
  `ghostscript` B&W engine (see Color/B&W).

These live behind a `lectern-slides[pdf]` install extra so the core stays light.

## Render-time options (change the master)

| Option | Effect |
| --- | --- |
| `backgrounds = true\|false` | `print_background` on/off **and** an injected print stylesheet that hides `data-background-*` and `.inverse` fills when off. Default `true`. |
| `light_inverse = true\|false` | Flip `.inverse` (dark) slides to light for ink economy, using the theme's own tokens (`--inverse-bg`→`--bg`, `--inverse-fg`→`--fg`). Default `false`. |
| `fragments = "flatten"\|"steps"` | Maps to reveal `pdfSeparateFragments`. `flatten` = one page per slide with all builds shown (handout default); `steps` = one page per build. |
| `paper = "deck"\|"letter"\|"a4"\|WxH` | `deck` (default) uses the slide aspect via `prefer_css_page_size` for the 1-up master; for a multi-up handout `deck` falls back to `letter` (a deck-shaped sheet leaves tiled slides tiny). Named sizes letterbox the slide for standard paper. |
| `posters = "auto"\|"explicit"\|"off"` | How live embeds become stills (next section). |

Because these change printed pixels, they are set when the master is rendered.
The pipeline injects a small print stylesheet built on the **theme token
contract**, so `light_inverse` / `backgrounds=off` work for any theme without the
theme needing its own print block (a theme MAY still add `@media print`
refinements; it's optional).

## Animations → a default frame

Live embeds (the D3 iframe today; WASM/WebGPU components later) can't animate in a
PDF, so each resolves to one deterministic still. Resolution order:

1. **Explicit poster.** `<iframe data-poster="assets/d3.png">` → that image is
   used. Most predictable; recommended for anything you care about exactly.
2. **Auto-capture** (`posters = "auto"`, the default). The pipeline loads the
   embed in headless Chromium with reduced-motion emulated and `?static=1`
   appended, waits `data-poster-at` ms (default 1200) — or for a
   `window.lecternReady === true` signal if the embed sets one — screenshots the
   embed's box to PNG, and swaps the `<iframe>` for an `<img>` in the print DOM.
3. **Static-mode passthrough** (`posters = "off"` or capture unavailable). The
   print render loads the embed with reduced-motion + `?static=1`; a well-behaved
   embed paints a single frame, which prints inline. (This already works for the
   sample's `d3-bars.html`, which honors `prefers-reduced-motion`.)

**Embed authoring contract** (so an embed produces a clean default frame):
- Honor `prefers-reduced-motion: reduce` **and** a `?static=1` query by drawing
  one deterministic frame and not looping.
- Optionally set `window.lecternReady = true` once that frame is painted, so
  auto-capture knows when to shoot instead of guessing with `data-poster-at`.

WebGPU/WASM note: headless Chromium needs ANGLE/SwiftShader flags
(`--enable-unsafe-swiftshader`) for GPU contexts, and late-painting components
should rely on explicit posters or `lecternReady` rather than a fixed delay.

## Layout: 1-up, 2-up, N-up, handouts (imposition)

The master is imposed onto sheets with pypdf (+ a reportlab overlay for chrome and
notes). Presets:

| `layout` | Sheet |
| --- | --- |
| `2up-notes` (**default**) | 2 slides stacked on a portrait page, each with its speaker notes beside it |
| `1up` | the master, unchanged — clean projection slides |
| `2up` | 2 slides stacked, no notes |
| `4up` / `2x2` | 4 slides, 2×2 |
| `6up` | 6 slides, 2×3 |
| `3up-notes` | 3 slides down the left, **speaker notes beside each** |

`2up-notes` is the default delivered layout: a portrait page holds two rows, each
row a slide thumbnail (~58% width, left) with its notes column (right). Use
`--layout 1up` when you want bare slides for projection. The notes are the real
ones Lectern already parses from `<!-- notes -->` / `::: notes`, so handouts carry
your script, not blank lines.

Imposition controls: `paper`, `orientation` (`auto` by default — the sheet is
turned to match the deck aspect, so wide 16:9 slides tile without big margins),
`margins`, `gutter`,
`frame = true|false` (hairline border per thumbnail), `slide_numbers`,
`header` / `footer` (e.g. title, date, page x/y). All vector; text stays
selectable.

## Color / B&W

Two engines, pick per taste:

- **`tokens` (default, no dependency).** The pipeline reads the active theme's
  color tokens, maps each to its perceptual-luminance gray, and injects the gray
  token set for the render. Vector, text stays crisp, and contrast is *designed*
  (the indigo and the vermilion seal become distinct grays rather than mud). Does
  **not** recolor embedded raster images / captured posters — those stay as-is.
- **`ghostscript` (full document).** Post-processes the finished PDF to DeviceGray,
  converting everything including raster posters and images. Needs the `gs`
  binary; use when you want guaranteed end-to-end grayscale.

`color = "color" | "bw"`; `bw_engine = "tokens" | "ghostscript"`.

Convenience preset: **`ink_saver = true`** = `bw` + `backgrounds = false` +
`light_inverse = true`. The handout-friendly default for printing.

## CLI & config

```
lectern build SOURCE -f pdf [--layout 1up] [--bw] [--no-backgrounds]
                            [--light-inverse] [--ink-saver] [--paper a4]
```

```toml
[pdf]
layout        = "2up-notes"  # 2up-notes (default) | 1up | 2up | 4up | 6up | 3up-notes
color         = "color"      # color | bw
bw_engine     = "tokens"     # tokens | ghostscript
backgrounds   = true
light_inverse = false
fragments     = "flatten"    # flatten | steps
paper         = "deck"       # deck | letter | a4 | 1280x720
posters       = "auto"       # auto | explicit | off
poster_at     = 1200         # ms, default capture moment for auto posters
tagged        = true         # emit a tagged (structured) PDF for screen readers;
                             # preserved by the 1up master, flattened by N-up imposition

# handout chrome (used by 2up/4up/6up/3up-notes)
frame         = true
slide_numbers = true
gutter        = "10mm"
header        = ""
footer        = "{title} · {date} · {page}/{pages}"
```

CLI flags override `[pdf]`, which overrides defaults. `--ink-saver` expands to the
three options above.

## Caching & determinism

The 1-up master is content-hashed and cached under the deck's `build_dir`
(`build/.lectern-cache/`). Re-exporting `2up` then `4up` then `--bw` re-runs only
imposition / conversion, not the (slow) Chromium render. Poster captures are
cached per embed + `poster_at`. A given deck + options always produces a
byte-stable master so diffs are meaningful. Because the cache lives in
`build_dir`, `lectern clean` (which clears `out_dir`) keeps it; `lectern clean
--all` drops it.

## Milestone mapping

- **M2** ships the 1-up vector master (`-f pdf`) — backgrounds toggle, fragments
  flatten, poster *passthrough* (reduced-motion static frames).
- A later milestone (**M6, PDF finishing**) adds imposition (N-up / `3up-notes`),
  the B&W engines, `light_inverse`, auto poster capture, and handout chrome.

# ROADMAP — Lectern

Sequenced high-leverage → speculative. v1 is Phases 0–1; everything after is a
designed seam, not present work. This mirrors the calls you made in the
Org/resource-oriented architecture discussion: build it as *your* tool, keep
slides static for a long time, and don't try to out-polish Slidev or out-render
Quarto for general use — win where your content is graph-shaped.

## Phase 0 — Assemble (v1 core)

The preprocessor is the whole point and the most reusable piece. Directory or
manifest of Markdown → one assembled deck, with transclusion, `#1-3,14` slide
ranges, partial search paths, and a source-map. Output is plain assembled
Markdown you can hand to *any* renderer (`lectern assemble`). Even if every
renderer choice changes later, this layer survives.

## Phase 1 — Render + watch (v1 core)

`reveal` adapter (native, no heavy deps), token-driven theming with Remark-parity
classes, asset resolution (local dir or URL), and a `--watch` server with SSE
live-reload and optional cross-origin-isolation headers. At the end of this
phase you can retire the manual NetKernel → DeckTape/print path for new decks.
Add the `remark` adapter so existing decks come along unchanged.

## Phase 2 — Output breadth

`marp` and `quarto` subprocess adapters for high-quality static HTML/PDF/PPTX
when you want them, behind `available()` guards. A distinctive named theme or two
beyond `base`. Still static content; still one author.

## Phase 3 — Components (the WASM/WebGPU seam, finally used)

Only now build the embed pipeline the dev server was prepared for:

- A `components/` directory of ES-module / WASM bundles copied into `dist/`.
- A neutral placeholder in Markdown — e.g. a fenced block
  ```` ```{component=webgpu-particles ...props} ```` or
  `<div data-component="…">` — that a small mount runtime wires to a module on
  the slide.
- The dev server already sets COOP/COEP under `[serve].coi`, so
  `SharedArrayBuffer`, WASM threads, and WebGPU contexts work.

Keep the explicit guardrail from your earlier reasoning: this handles *embedded
interactive views* (a WebGPU canvas, a Rust/WASM demo, a Bevy export). It does
**not** attempt animation *timelines* — cross-slide choreography with state and
duration is a separate, harder design and stays out of scope until there's a
concrete talk that demands it.

## Phase 4 — Graph source backend (the convergence)

Swap `FilesystemSource` for a `CmsSource` implementing the same `Source`
protocol against your semantic CMS: partials, slides, and assets resolve by
URI/query against the RDF graph instead of the filesystem. A deck becomes "resolve
this composition of nodes, ordered for this audience," projected through the same
preprocess→render pipeline. Markdown stays a first-class authoring surface and a
"degenerate linear chain" view of the graph; the graph becomes the source of
truth. Nothing in preprocess/render/serve should need to change — that's the
test of whether the Phase 0–1 seams were drawn correctly.

## Explicitly deferred / out of scope

- Animation timelines and choreography (Phase 3 note above).
- Multi-user, auth, hosted service, plugin ecosystem.
- A web authoring editor (your authoring lives in Emacs/Org-Roam).
- Trying to be a general-purpose Slidev/Quarto replacement.

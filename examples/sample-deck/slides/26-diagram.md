# Diagrams — Mermaid

A fenced ` ```mermaid ` block renders to a diagram, themed from the deck's design
tokens — live in the deck **and** in the vector PDF. No iframe, no setup; the
renderer loads Mermaid only when a diagram is present.

```mermaid
flowchart LR
  accTitle: Lectern's assemble-and-render pipeline
  accDescr: Markdown is assembled into one deck, then rendered to either reveal HTML or a vector PDF.
  MD[Markdown] --> A[assemble]
  A --> R{render}
  R --> H[reveal HTML]
  R --> P[vector PDF]
```

<!-- @from slides/00-intro.md slide=1 -->
<!-- slide: .center .middle -->

# Fixture Deck

A deck that exercises includes, ranges, partials, notes, and raw HTML.

<!-- notes -->
This speaker note should survive assembly untouched.
<!-- /notes -->
---
<!-- @from _partials/lib.md slide=1 -->
# Lib One

First library slide.

---
<!-- @from _partials/lib.md slide=3 -->

# Lib Three

Third library slide.

---
<!-- @from _partials/lib.md slide=4 -->

# Lib Four

Fourth library slide.
---
<!-- @from slides/20-fence.md slide=1 -->
# Fence + Inline Include

<!-- @from _partials/note.md slide=1 -->
> A reusable note, included inline by another slide.

The fenced block below contains a line that looks like a slide break; the
fence-aware splitter must keep this all on one slide:

```text
not --- a slide break
---
still inside the code fence
```
---
<!-- @from slides/30-canvas.md slide=1 -->
<!-- slide: .inverse #demo -->

# Raw HTML Passthrough

<canvas id="demo-canvas" width="320" height="180"></canvas>
<script type="module">
  const c = document.getElementById("demo-canvas");
  // A real embed would draw here; assembly must pass this through untouched.
</script>

<!-- A seven-slide source library. The deck pulls only slides 2-3 and 6 from it
     via a ranged include in deck.toml (`_partials/principles.md#2-3,6`). Each
     slide announces its own number, so the selection is visible in the deck:
     2 / 7, 3 / 7, and 6 / 7 appear; 1, 4, 5, and 7 do not. -->

<!-- slide: .center .middle .on-dark data-background-color="#1f2430" -->

# 1 / 7

The title card — *skipped* by the include.

---

<!-- slide: .center .middle -->

# 2 / 7 · Transclusion

One source file, reused across decks. `#2-3` grabbed this slide and the next as
a contiguous range.

---

<!-- slide: .center .middle -->

# 3 / 7 · Ranges are inclusive

`A-B` includes both ends — so `#2-3` means slides **two and three**, the second
half of that range.

---

<!-- slide: .center .middle -->

# 4 / 7

A slide the include left behind.

---

<!-- slide: .center .middle -->

# 5 / 7

Another one not selected.

---

<!-- slide: .center .middle -->

# 6 / 7 · Pick by index

`,6` appends a single slide after the range — the full spec was `#2-3,6`.

---

<!-- slide: .center .middle .on-dark data-background-color="#1f2430" -->

# 7 / 7

The closer — also skipped.

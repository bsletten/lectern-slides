# Syntax Highlighting

Fenced code is tokenized by reveal's highlight plugin and colored by the theme —
here's Lectern's own slide-range parser:

```python
def parse_ranges(spec: str, n: int) -> list[int]:
    """Expand '1-3,14' into 1-based slide indices, bounded by n."""
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:                       # a range like 1-3 or 5-
            lo, hi = part.split("-")
            out += range(int(lo or 1), int(hi or n) + 1)
        else:                                  # a single slide
            out.append(int(part))
    return [i for i in out if 1 <= i <= n]
```

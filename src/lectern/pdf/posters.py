"""Live embeds → one deterministic still, in the print DOM.

An ``<iframe>`` (a D3/WebGPU/WASM demo) can't animate in a PDF, so before the
master is printed each embed resolves to a single frame (``PDF-EXPORT.md`` §
Animations). Resolution order: an explicit ``data-poster`` image wins; otherwise
(``posters="auto"``) the embed is loaded with reduced-motion + ``?static=1``,
given until ``window.lecternReady`` or ``data-poster-at`` ms, screenshotted, and
the ``<iframe>`` swapped for an ``<img>``. With ``posters="off"`` nothing is
swapped — a well-behaved embed paints its own static frame and prints inline.

Runs against the live Playwright ``page`` during the master render; failures warn
and leave the embed as-is rather than aborting the export.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .options import PdfOptions

_COLLECT_EMBEDS = """
() => Array.from(document.querySelectorAll('iframe')).map((el, i) => {
  el.setAttribute('data-lectern-embed', String(i));
  const r = el.getBoundingClientRect();
  return {
    i,
    poster: el.getAttribute('data-poster'),
    at: parseInt(el.getAttribute('data-poster-at') || '0', 10),
  };
})
"""


def _swap_to_image(page, index: int, src: str) -> None:
    page.eval_on_selector(
        f"iframe[data-lectern-embed='{index}']",
        """(el, src) => {
            const img = document.createElement('img');
            img.src = src;
            img.style.width = el.style.width || el.getAttribute('width') || '100%';
            img.style.height = el.style.height || el.getAttribute('height') || 'auto';
            el.replaceWith(img);
        }""",
        arg=src,
    )


def capture_into(
    page, options: PdfOptions, default_at: int, warnings: list[str]
) -> int:
    """Resolve embeds to stills on ``page``; return how many were swapped."""
    if options.posters == "off":
        return 0
    try:
        embeds = page.evaluate(_COLLECT_EMBEDS)
    except Exception:  # pragma: no cover - defensive
        return 0

    swapped = 0
    for embed in embeds:
        index = embed["i"]
        try:
            if embed["poster"]:
                _swap_to_image(page, index, embed["poster"])
                swapped += 1
                continue
            if options.posters == "explicit":
                continue  # only honor explicit posters; leave others to static mode
            handle = page.query_selector(f"iframe[data-lectern-embed='{index}']")
            if handle is None:
                continue
            page.wait_for_timeout(embed["at"] or default_at)
            png = handle.screenshot()
            data_uri = "data:image/png;base64," + _b64(png)
            _swap_to_image(page, index, data_uri)
            swapped += 1
        except Exception as e:  # pragma: no cover - defensive
            warnings.append(f"pdf: poster capture for embed #{index} failed ({e})")
    return swapped


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")

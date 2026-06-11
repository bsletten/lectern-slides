"""The 1-up vector master — print the reveal deck in headless Chromium.

Playwright drives Chromium's ``page.pdf`` (vector, honors reveal's ``@page`` and
``print_background``); appending ``?print-pdf`` puts reveal into its one-slide-
per-page print layout. Everything heavy is imported lazily so the core install
never needs Playwright, and a missing browser binary surfaces as a clear
:class:`~lectern.errors.RenderError` with the install command, not a traceback.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import RenderError

_INSTALL_HINT = (
    "PDF export needs the optional extra and a browser: "
    "`pip install 'lectern-slides[pdf]'` then `playwright install chromium`"
)


def ensure_available() -> None:
    """Raise :class:`RenderError` unless Playwright (and a browser) is usable."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RenderError(f"Playwright is not installed. {_INSTALL_HINT}") from None
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as e:  # browser missing / launch failure
        raise RenderError(
            f"could not launch headless Chromium ({e}). {_INSTALL_HINT}"
        ) from e


def print_to_pdf(
    html_path: Path,
    *,
    print_background: bool,
    settle_ms: int = 300,
    swiftshader: bool = False,
    prepare=None,
) -> bytes:
    """Render ``html_path`` (with ``?print-pdf``) to vector PDF bytes.

    Waits for the network to go idle (reveal.js + CSS load from CDN) and for a
    short settle so fonts/highlighting paint, then prints at reveal's own page
    size via ``prefer_css_page_size``. ``prepare(page)`` runs after print media is
    emulated and before printing — the seam where poster capture swaps embeds.
    """
    from playwright.sync_api import sync_playwright

    url = html_path.resolve().as_uri() + "?print-pdf"
    args = ["--enable-unsafe-swiftshader"] if swiftshader else []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=args)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.emulate_media(media="print", reduced_motion="reduce")
            if settle_ms:
                page.wait_for_timeout(settle_ms)
            if prepare is not None:
                prepare(page)
            data = page.pdf(
                print_background=print_background, prefer_css_page_size=True
            )
            browser.close()
            return data
    except RenderError:
        raise
    except Exception as e:
        raise RenderError(f"Chromium PDF render failed: {e}") from e

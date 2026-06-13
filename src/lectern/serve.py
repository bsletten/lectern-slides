"""Live-preview server for ``lectern watch``.

Builds the deck once, serves ``out_dir`` over a small Starlette/Uvicorn app, and
watches the deck's sources with ``watchfiles``. On every change it re-assembles
and re-renders; on success it pushes a ``reload`` to connected browsers over SSE,
and on failure it pushes the error so the page shows an in-page overlay instead
of the server crashing.

The pieces are deliberately separable so they can be tested without standing up
a real server: :func:`inject_livereload`, :func:`format_sse`, and
:meth:`LiveReloadServer.build` / :meth:`LiveReloadServer.app` are all exercised
directly in the tests; only :meth:`LiveReloadServer.run` (uvicorn + the watch
loop) is integration-only.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import webbrowser
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from starlette.routing import Route

from .config import resolve_source
from .errors import LecternError
from .preprocess import assemble_resolved
from .render import get_renderer
from .theming import is_theme_path

SSE_PATH = "/__lectern__/reload"

# Injected before </body> in every served HTML page. A tiny EventSource client:
# reload on a successful rebuild, show an overlay on a build error.
_LIVE_RELOAD = """
<style id="__lectern_overlay_style">
#__lectern_overlay { position: fixed; inset: 0; z-index: 2147483647;
  background: rgba(18,10,12,.95); color: #ffd9d9; padding: 2.2rem 2.4rem;
  font: 13px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; overflow: auto; }
#__lectern_overlay h2 { margin: 0 0 1rem; color: #ff9a9a;
  font: 600 15px/1.3 system-ui, sans-serif; }
#__lectern_overlay pre { white-space: pre-wrap; word-break: break-word; margin: 0; }
#__lectern_overlay[hidden] { display: none; }
</style>
<div id="__lectern_overlay" hidden>
  <h2>Build error</h2>
  <pre id="__lectern_overlay_msg"></pre>
</div>
<script>
(function () {
  var ov = document.getElementById('__lectern_overlay');
  var msg = document.getElementById('__lectern_overlay_msg');
  function show(t) { msg.textContent = t; ov.hidden = false; }
  if (window.__lectern_error) show(window.__lectern_error);
  try {
    var es = new EventSource('__SSE_PATH__');
    es.addEventListener('reload', function () { location.reload(); });
    es.addEventListener('builderror', function (e) { show(e.data); });
  } catch (err) { /* SSE unavailable; static preview still works */ }
})();
</script>
"""


def inject_livereload(html: str, error: str | None) -> str:
    """Insert the live-reload client (and a pre-shown overlay on *error*)."""
    snippet = _LIVE_RELOAD.replace("__SSE_PATH__", SSE_PATH)
    if error:
        snippet = (
            f"<script>window.__lectern_error = {json.dumps(error)};</script>\n{snippet}"
        )
    if "</body>" in html:
        return html.replace("</body>", f"{snippet}\n</body>", 1)
    return html + snippet


def format_sse(event: str, data: str) -> str:
    """Format one Server-Sent Event (multi-line data is split per the spec)."""
    lines = "\n".join(f"data: {line}" for line in data.splitlines() or [""])
    return f"event: {event}\n{lines}\n\n"


# macOS application names for common browsers, so `[serve].browser = "chrome"`
# opens Google Chrome via `open -a` even when it isn't a registered webbrowser.
_MAC_BROWSER_APPS = {
    "chrome": "Google Chrome",
    "google-chrome": "Google Chrome",
    "chromium": "Chromium",
    "firefox": "Firefox",
    "safari": "Safari",
    "edge": "Microsoft Edge",
    "brave": "Brave Browser",
}


def open_in_browser(url: str, browser: str | None = None) -> None:
    """Open *url* in a named *browser* if given, else the system default.

    Tries the cross-platform ``webbrowser`` registry first; on macOS falls back to
    ``open -a <App>`` (mapping short names like ``chrome`` to their app names), and
    finally to the default browser.
    """
    if not browser:
        webbrowser.open(url)
        return
    with contextlib.suppress(Exception):
        webbrowser.get(browser).open(url)
        return
    if sys.platform == "darwin":
        import subprocess

        app = _MAC_BROWSER_APPS.get(browser.lower(), browser)
        with contextlib.suppress(Exception):
            subprocess.run(["open", "-a", app, url], check=True)
            return
    webbrowser.open(url)  # last resort: the default browser


def _fallback_shell(error: str | None) -> str:
    """A minimal page to serve before the first successful build."""
    state = (
        "Build failed — see the overlay." if error else "Waiting for the first build…"
    )
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<title>Lectern</title></head><body>"
        f"<p style='font:15px system-ui;color:#666;padding:2rem'>{state}</p>"
        "</body></html>"
    )


def watch_paths(resolved) -> list[Path]:
    """Directories to watch: the deck root, external partial dirs, and an

    external local ``asset_base`` / theme (anything under the root is already
    covered by the recursive root watch).
    """
    paths: list[Path] = [resolved.root]
    for d in resolved.partial_dirs:
        if d.is_dir():
            paths.append(d)

    cfg = resolved.config
    if cfg.asset_base and not cfg.asset_base.lower().startswith(
        ("http://", "https://", "//")
    ):
        base = Path(cfg.asset_base).expanduser()
        base = base if base.is_absolute() else resolved.root / base
        if base.is_dir():
            paths.append(base)

    if is_theme_path(cfg.theme):
        theme = Path(cfg.theme).expanduser()
        theme = theme if theme.is_absolute() else resolved.root / theme
        if theme.parent.is_dir():
            paths.append(theme.parent)

    # De-duplicate while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(rp)
    return unique


class LiveReloadServer:
    """Serves ``out_dir`` with live reload and rebuilds on source changes."""

    def __init__(
        self,
        source: str | Path,
        out_dir: Path,
        *,
        host: str = "127.0.0.1",
        port: int = 8080,
        coi: bool = False,
        open_browser: bool = True,
        browser: str | None = None,
        config_override: str | Path | None = None,
        cli_overrides: dict | None = None,
        watch: list[Path] | None = None,
    ):
        self.source = source
        self.out_dir = out_dir
        self.host = host
        self.port = port
        self.open_browser = open_browser
        self.browser = browser
        self.config_override = config_override
        self.cli_overrides = cli_overrides
        self.watch = watch or []
        self.error: str | None = None
        self.warnings: list[str] = []
        self._clients: set[asyncio.Queue] = set()
        self._coi_headers = (
            {
                "Cross-Origin-Opener-Policy": "same-origin",
                "Cross-Origin-Embedder-Policy": "require-corp",
            }
            if coi
            else {}
        )

    # --- build -----------------------------------------------------------
    def build(self) -> None:
        """Re-resolve, assemble, and render. Records the error on failure."""
        try:
            resolved = resolve_source(
                self.source,
                config_override=self.config_override,
                cli_overrides=self.cli_overrides,
            )
            deck = assemble_resolved(resolved)
            adapter = get_renderer(resolved.config.renderer)
            result = adapter.render(deck, resolved.config, self.out_dir)
            self.error = None
            self.warnings = result.warnings
        except LecternError as e:
            self.error = e.render()

    # --- ASGI app --------------------------------------------------------
    def app(self) -> Starlette:
        return Starlette(
            routes=[
                Route(SSE_PATH, self._sse),
                Route("/{path:path}", self._serve_file),
            ]
        )

    def _headers(self, extra: dict | None = None) -> dict:
        headers = dict(self._coi_headers)
        if extra:
            headers.update(extra)
        return headers

    async def _serve_file(self, request: Request) -> Response:
        rel = request.path_params["path"] or "index.html"
        out_root = self.out_dir.resolve()
        target = (self.out_dir / rel).resolve()

        # Reject path traversal outside the output directory.
        if out_root not in target.parents and target != out_root:
            return HTMLResponse("forbidden", status_code=403, headers=self._headers())

        if target.is_dir():
            target = target / "index.html"

        is_html = target.suffix in (".html", ".htm") or rel in ("", "index.html")
        if is_html:
            base = (
                target.read_text(encoding="utf-8")
                if target.is_file()
                else _fallback_shell(self.error)
            )
            page = inject_livereload(base, self.error)
            return HTMLResponse(
                page, headers=self._headers({"Cache-Control": "no-store"})
            )

        if target.is_file():
            return FileResponse(target, headers=self._headers())

        return HTMLResponse("not found", status_code=404, headers=self._headers())

    async def _events(self, queue: asyncio.Queue):
        """Yield SSE chunks for one client: greet with any error, then stream."""
        # Greet new clients with the current error, if any.
        if self.error:
            yield format_sse("builderror", self.error)
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=15)
                yield format_sse(event, data)
            except TimeoutError:
                yield ": keepalive\n\n"

    async def _sse(self, request: Request) -> StreamingResponse:
        queue: asyncio.Queue = asyncio.Queue()
        self._clients.add(queue)

        async def stream():
            try:
                async for chunk in self._events(queue):
                    yield chunk
            finally:
                self._clients.discard(queue)

        headers = self._headers(
            {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
        )
        return StreamingResponse(
            stream(), media_type="text/event-stream", headers=headers
        )

    def _notify(self) -> None:
        event, data = ("builderror", self.error) if self.error else ("reload", "1")
        for queue in list(self._clients):
            queue.put_nowait((event, data))

    # --- run (integration) ----------------------------------------------
    def run(self) -> None:
        import uvicorn

        self.build()
        url = f"http://{self.host}:{self.port}/"
        status = "build OK" if self.error is None else f"build error: {self.error}"
        print(f"lectern: serving {self.out_dir} at {url} ({status})", file=sys.stderr)
        for w in self.warnings:
            print(f"warning: {w}", file=sys.stderr)

        config = uvicorn.Config(
            self.app(), host=self.host, port=self.port, log_level="warning"
        )
        server = uvicorn.Server(config)
        asyncio.run(self._run(server))

    async def _run(self, server) -> None:
        stop = asyncio.Event()
        watch_task = asyncio.create_task(self._watch_loop(stop))
        if self.open_browser:
            asyncio.create_task(self._open_later())
        try:
            await server.serve()
        finally:
            stop.set()
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task

    async def _open_later(self) -> None:
        await asyncio.sleep(0.6)
        with contextlib.suppress(Exception):
            open_in_browser(f"http://{self.host}:{self.port}/", self.browser)

    async def _watch_loop(self, stop: asyncio.Event) -> None:
        from watchfiles import awatch

        async for _changes in awatch(
            *self.watch, watch_filter=self._change_filter, stop_event=stop
        ):
            self.build()
            if self.error:
                print(f"lectern: rebuild failed: {self.error}", file=sys.stderr)
            self._notify()

    def _change_filter(self, _change, path: str) -> bool:
        p = Path(path)
        out = self.out_dir.resolve()
        rp = p.resolve()
        if out == rp or out in rp.parents:
            return False  # ignore our own output writes (would loop forever)
        parts = set(p.parts)
        if parts & {".git", "__pycache__", ".pytest_cache", "node_modules"}:
            return False
        return not p.name.startswith(".")

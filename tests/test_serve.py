"""Live-preview server: app behavior, injection, overlay, COI, SSE, watch paths."""

import asyncio

from conftest import write
from starlette.testclient import TestClient

from lectern.config import resolve_source
from lectern.serve import (
    SSE_PATH,
    LiveReloadServer,
    format_sse,
    inject_livereload,
    watch_paths,
)


def _server(source, out_dir, **kwargs) -> LiveReloadServer:
    return LiveReloadServer(source, out_dir=out_dir, open_browser=False, **kwargs)


# --- pure helpers --------------------------------------------------------
def test_inject_livereload_adds_client_before_body():
    out = inject_livereload("<html><body>hi</body></html>", error=None)
    assert SSE_PATH in out
    assert "EventSource" in out
    assert out.index("EventSource") < out.index("</body>")
    assert "window.__lectern_error =" not in out  # no pre-set error assignment


def test_inject_livereload_preshows_error():
    out = inject_livereload("<html><body></body></html>", error="boom: bad/range")
    assert "window.__lectern_error =" in out  # the error is assigned for display
    assert "boom: bad/range" in out  # JSON-encoded into the page


def test_format_sse_single_and_multiline():
    assert format_sse("reload", "1") == "event: reload\ndata: 1\n\n"
    assert format_sse("builderror", "a\nb") == "event: builderror\ndata: a\ndata: b\n\n"


def test_watch_paths_includes_partials_excludes_url_base(tmp_path):
    lib = tmp_path / "shared"
    write(lib, "x.md", "x")
    write(
        tmp_path,
        "deck.toml",
        'partials = ["./shared"]\nasset_base = "https://cms/x"\nslides = ["a.md"]\n',
    )
    write(tmp_path, "a.md", "# A")
    resolved = resolve_source(tmp_path)
    paths = watch_paths(resolved)
    assert tmp_path.resolve() in paths
    assert lib.resolve() in paths
    # A URL asset_base contributes no local watch path.
    assert all("cms" not in str(p) for p in paths)


# --- build state ---------------------------------------------------------
def test_build_sets_and_clears_error(fixtures, tmp_path):
    server = _server(fixtures / "render-deck", tmp_path)
    server.build()
    assert server.error is None
    assert (tmp_path / "index.html").is_file()


def test_build_honors_renderer_override(fixtures, tmp_path):
    # `lectern watch -r remark` routes the override through to rebuilds.
    server = _server(
        fixtures / "render-deck", tmp_path, cli_overrides={"renderer": "remark"}
    )
    server.build()
    assert server.error is None
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "remarkjs.com" in html  # the remark adapter rendered, not reveal


def test_build_records_error_without_crashing(tmp_path):
    write(tmp_path, "main.md", "# A\n\n<!-- include: missing.md -->\n")
    server = _server(tmp_path / "main.md", tmp_path / "out")
    server.build()
    assert server.error is not None
    assert "missing.md" in server.error


# --- ASGI app ------------------------------------------------------------
def test_serves_index_with_injected_client(fixtures, tmp_path):
    server = _server(fixtures / "render-deck", tmp_path)
    server.build()
    client = TestClient(server.app())
    r = client.get("/")
    assert r.status_code == 200
    assert "Hero Slide" in r.text  # reveal content present
    assert SSE_PATH in r.text  # live-reload client injected
    assert r.headers["cache-control"] == "no-store"


def test_serves_copied_asset(fixtures, tmp_path):
    server = _server(fixtures / "render-deck", tmp_path)
    server.build()
    client = TestClient(server.app())
    asset = next((tmp_path / "assets").iterdir())
    r = client.get(f"/assets/{asset.name}")
    assert r.status_code == 200


def test_missing_path_is_404(fixtures, tmp_path):
    server = _server(fixtures / "render-deck", tmp_path)
    server.build()
    client = TestClient(server.app())
    assert client.get("/nope.png").status_code == 404


def test_coi_headers_toggle(fixtures, tmp_path):
    on = _server(fixtures / "render-deck", tmp_path, coi=True)
    on.build()
    r = TestClient(on.app()).get("/")
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert r.headers["cross-origin-embedder-policy"] == "require-corp"

    off = _server(fixtures / "render-deck", tmp_path)
    off.build()
    r2 = TestClient(off.app()).get("/")
    assert "cross-origin-opener-policy" not in r2.headers


def test_overlay_shown_when_build_errored(tmp_path):
    server = _server(tmp_path / "main.md", tmp_path / "out")
    write(tmp_path, "main.md", "# A\n\n<!-- include: missing.md -->\n")
    server.build()  # error -> no index.html, fallback shell
    client = TestClient(server.app())
    r = client.get("/")
    assert r.status_code == 200
    assert "window.__lectern_error" in r.text
    assert "missing.md" in r.text


def test_notify_broadcasts_reload_or_error(fixtures, tmp_path):
    server = _server(fixtures / "render-deck", tmp_path)
    queue: asyncio.Queue = asyncio.Queue()
    server._clients.add(queue)

    server.error = None
    server._notify()
    assert queue.get_nowait() == ("reload", "1")

    server.error = "bad/range"
    server._notify()
    assert queue.get_nowait() == ("builderror", "bad/range")


def test_sse_stream_greets_with_error_then_streams(fixtures, tmp_path):
    async def go():
        server = _server(fixtures / "render-deck", tmp_path)
        server.error = "boom"
        queue: asyncio.Queue = asyncio.Queue()
        gen = server._events(queue)
        # New client is greeted with the current error immediately.
        first = await asyncio.wait_for(gen.__anext__(), timeout=1)
        assert "builderror" in first and "boom" in first
        # A subsequent broadcast is streamed.
        await queue.put(("reload", "1"))
        nxt = await asyncio.wait_for(gen.__anext__(), timeout=1)
        assert nxt == format_sse("reload", "1")
        await gen.aclose()

    asyncio.run(go())

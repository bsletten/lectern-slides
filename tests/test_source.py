"""The ``Source`` seam: IRI keys, themes/assets through the source, KernelSource.

The load-bearing check is :func:`test_kernel_deck_renders_identically_to_disk`:
a deck whose slides, theme and assets all come from kernel resources renders to
the same HTML and the same asset bytes as the identical deck on disk.
"""

from pathlib import Path

import pytest
from conftest import FIXTURES, write

from lectern import a11y
from lectern.assets import AssetResolver
from lectern.config import resolve_source
from lectern.errors import ConfigError
from lectern.preprocess import assemble_resolved
from lectern.render import get_renderer
from lectern.source import FilesystemSource, KernelSource, Source, is_iri
from lectern.theming import build_theme, resolve_theme_css

BASE = "urn:lectern:test-deck/"
KROOT = Path("/kernel/deck")


def _deck(root: Path) -> Path:
    """A deck exercising a path theme, a ranged partial, deck-local and
    asset_base assets, and a raw-HTML attribute ref."""
    write(
        root,
        "deck.toml",
        'title = "Kernel Parity"\n'
        'renderer = "reveal"\n'
        'theme = "./themes/house.css"\n'
        'asset_base = "./assets"\n'
        'partials = ["_partials"]\n'
        'slides = ["slides/01-title.md", "slides/02-body.md#2"]\n',
    )
    write(
        root,
        "themes/house.css",
        ":root { --bg: #ffffff; --fg: #111111; --accent: #0050aa; }\n"
        ".reveal { color: var(--fg); }\n",
    )
    write(
        root,
        "slides/01-title.md",
        "# Kernel Parity\n\n![logo](images/qr.svg)\n\n<!-- include: shared.md#1 -->\n",
    )
    write(
        root,
        "slides/02-body.md",
        "# Skipped\n\n---\n\n# Body\n\n![grid](grid.svg)\n\n"
        '<img src="/logo.png" alt="logo">\n\n???\nA note.\n',
    )
    write(root, "_partials/shared.md", "# Shared\n\nfrom a partial\n\n---\n\n# Two\n")
    write(root, "images/qr.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>\n')
    write(
        root, "assets/grid.svg", (FIXTURES / "render-deck/assets/grid.svg").read_text()
    )
    (root / "assets/logo.png").write_bytes(
        (FIXTURES / "render-deck/assets/logo.png").read_bytes()
    )
    return root


def _kernel_from_dir(root: Path) -> KernelSource:
    """Stage every file of a deck dir as a kernel resource under ``BASE``."""
    items = {
        BASE + p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }
    return KernelSource.from_mapping(items, BASE, KROOT)


def _render(source, src: Source, out_dir: Path):
    resolved = resolve_source(source, src=src)
    deck = assemble_resolved(resolved, src=src)
    adapter = get_renderer(resolved.config.renderer)
    result = adapter.render(deck, resolved.config, out_dir)
    return deck, result


def _assets(out_dir: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted((out_dir / "assets").iterdir())}


# -- the done-when check ------------------------------------------------------


def test_kernel_deck_renders_identically_to_disk(tmp_path):
    disk = _deck(tmp_path / "disk")
    kernel = _kernel_from_dir(disk)

    disk_deck, disk_result = _render(disk, FilesystemSource(), tmp_path / "out-disk")
    k_deck, k_result = _render(KROOT, kernel, tmp_path / "out-kernel")

    disk_html = disk_result.output.read_text(encoding="utf-8")
    k_html = k_result.output.read_text(encoding="utf-8")
    assert k_html == disk_html
    assert "--accent: #0050aa" in k_html  # the deck theme, not the bundled one
    assert _assets(tmp_path / "out-kernel") == _assets(tmp_path / "out-disk")
    assert len(_assets(tmp_path / "out-kernel")) == 3  # qr.svg, grid.svg, logo.png
    assert k_deck.markdown(provenance=False) == disk_deck.markdown(provenance=False)
    assert k_result.warnings == disk_result.warnings
    assert a11y.audit(k_deck) == a11y.audit(disk_deck)


def test_kernel_deck_needs_no_local_files(tmp_path):
    """Nothing under the virtual root exists on disk; every read is the kernel's."""
    disk = _deck(tmp_path / "disk")
    kernel = _kernel_from_dir(disk)
    assert not KROOT.exists()
    _, result = _render(KROOT, kernel, tmp_path / "out")
    assert "Kernel Parity" in result.output.read_text(encoding="utf-8")


def test_kernel_directory_mode_lists_markdown_in_order(tmp_path):
    kernel = KernelSource.from_mapping(
        {
            BASE + "02-b.md": "# B\n",
            BASE + "01-a.md": "# A\n",
            BASE + "notes.txt": "skip",
            BASE + "sub/03-c.md": "# nested, not listed\n",
        },
        BASE,
        KROOT,
    )
    assert kernel.list(KROOT) == [KROOT / "01-a.md", KROOT / "02-b.md"]
    resolved = resolve_source(KROOT, src=kernel)
    assert resolved.entries == ["01-a.md", "02-b.md"]
    deck = assemble_resolved(resolved, src=kernel)
    assert deck.slide_count == 2


# -- IRI keying ---------------------------------------------------------------


def test_is_iri():
    assert is_iri("urn:deck:x")
    assert is_iri("https://example.org/deck/a.md")
    assert is_iri("file:///tmp/a.md")
    assert not is_iri(Path("/tmp/a.md"))
    assert not is_iri("slides/a.md")
    assert not is_iri("C:\\deck\\a.md")  # a drive letter is not a scheme


def test_kernel_source_answers_by_iri_and_by_path():
    kernel = KernelSource.from_mapping({BASE + "slides/a b.md": "# A\n"}, BASE, KROOT)
    assert kernel.iri(KROOT / "slides/a b.md") == BASE + "slides/a%20b.md"
    kernel = KernelSource.from_mapping({BASE + "slides/a.md": "# A\n"}, BASE, KROOT)
    assert kernel.read(KROOT / "slides/a.md") == "# A\n"
    assert kernel.read(BASE + "slides/a.md") == "# A\n"
    assert kernel.read_bytes(BASE + "slides/a.md") == b"# A\n"
    assert kernel.exists(KROOT / "slides/a.md")
    assert kernel.exists(BASE + "slides/a.md")
    assert not kernel.exists(KROOT / "slides/missing.md")
    assert kernel.path(BASE + "slides/a.md") == KROOT / "slides/a.md"


def test_kernel_source_refuses_paths_outside_its_root():
    kernel = KernelSource.from_mapping({BASE + "a.md": "x"}, BASE, KROOT)
    assert kernel.iri(Path("/etc/passwd")) is None
    assert not kernel.exists(Path("/etc/passwd"))
    assert not kernel.exists(KROOT / "../a.md")
    with pytest.raises(FileNotFoundError):
        kernel.read(Path("/etc/passwd"))


def test_kernel_source_requires_an_iri_base():
    with pytest.raises(ValueError):
        KernelSource.from_mapping({}, "not-an-iri")


def test_filesystem_source_accepts_file_iris(tmp_path):
    p = write(tmp_path, "a b.md", "# A\n")
    src = FilesystemSource()
    assert src.read(p.as_uri()) == "# A\n"
    assert src.exists(p.as_uri())
    assert not src.exists("urn:not:a:file")
    with pytest.raises(ValueError):
        src.read("urn:not:a:file")


# -- themes and assets go through the Source -----------------------------------


class _Recording:
    """Wraps a source and records every key asked of it."""

    def __init__(self, inner: Source):
        self.inner = inner
        self.asked: list = []

    def read(self, key):
        self.asked.append(("read", key))
        return self.inner.read(key)

    def read_bytes(self, key):
        self.asked.append(("read_bytes", key))
        return self.inner.read_bytes(key)

    def exists(self, key):
        self.asked.append(("exists", key))
        return self.inner.exists(key)

    def list(self, directory):
        return self.inner.list(directory)


def test_path_theme_is_read_through_the_source(tmp_path):
    kernel = KernelSource.from_mapping(
        {BASE + "themes/k.css": ":root { --fg: #123456; }\n"}, BASE, KROOT
    )
    name, css = resolve_theme_css("./themes/k.css", KROOT, (), kernel)
    assert (name, css) == ("k", ":root { --fg: #123456; }\n")
    theme = build_theme("./themes/k.css", "16:9", KROOT, None, kernel)
    assert theme.css.startswith(":root { --fg: #123456; }")


def test_named_theme_in_theme_dirs_is_read_through_the_source():
    kernel = KernelSource.from_mapping(
        {BASE + "lib/house.css": ".house{}\n"}, BASE, KROOT
    )
    assert resolve_theme_css("house", KROOT, [KROOT / "lib"], kernel) == (
        "house",
        ".house{}\n",
    )


def test_bundled_theme_still_falls_back_to_package_data():
    kernel = KernelSource.from_mapping({}, BASE, KROOT)
    name, css = resolve_theme_css("base", KROOT, [KROOT / "lib"], kernel)
    assert name == "base" and "--" in css


def test_missing_theme_through_source_is_a_config_error():
    kernel = KernelSource.from_mapping({}, BASE, KROOT)
    with pytest.raises(ConfigError, match="theme file not found"):
        resolve_theme_css("./themes/none.css", KROOT, (), kernel)


def test_assets_are_read_through_the_source(tmp_path):
    kernel = KernelSource.from_mapping(
        {BASE + "assets/pic.png": b"\x89PNG-bytes"}, BASE, KROOT
    )
    rec = _Recording(kernel)
    resolver = AssetResolver(KROOT, "./assets", tmp_path / "out", [], rec)
    new = resolver.resolve("pic.png", KROOT / "slides", "slides/a.md:1")
    assert new.startswith("assets/pic-") and new.endswith(".png")
    assert (tmp_path / "out" / new).read_bytes() == b"\x89PNG-bytes"
    assert ("read_bytes", KROOT / "assets/pic.png") in rec.asked


def test_filesystem_build_asks_the_source_for_theme_and_assets(tmp_path):
    """The renderer uses the deck's Source; disk output is unchanged."""
    disk = _deck(tmp_path / "disk")
    rec = _Recording(FilesystemSource())
    _render(disk, rec, tmp_path / "out")
    read = {k for op, k in rec.asked if op in ("read", "read_bytes")}
    root = disk.resolve()
    assert root / "themes/house.css" in read
    assert root / "assets/logo.png" in read
    assert root / "images/qr.svg" in read


# -- KernelSource edge cases ---------------------------------------------------


@pytest.mark.parametrize("base", ["urn:deck:x:", "urn:deck:x/"])
def test_kernel_directory_mode_under_any_base_separator(base):
    """A base ending in ``:`` or ``/`` lists the deck's slides either way."""
    kernel = KernelSource.from_mapping(
        {base + "02-b.md": "# B\n", base + "01-a.md": "# A\n"}, base, KROOT
    )
    assert kernel.list(KROOT) == [KROOT / "01-a.md", KROOT / "02-b.md"]
    resolved = resolve_source(KROOT, src=kernel)
    assert resolved.entries == ["01-a.md", "02-b.md"]


def test_kernel_subdirectory_under_colon_base_gets_a_slash():
    base = "urn:deck:x:"
    kernel = KernelSource.from_mapping(
        {base + "sub/a.md": "# A\n", base + "subway.md": "# no\n"}, base, KROOT
    )
    assert kernel.list(KROOT / "sub") == [KROOT / "sub/a.md"]


def test_kernel_relative_root_matches_the_absolute_deck_root(tmp_path, monkeypatch):
    """resolve_source makes the deck root absolute; a relative root still matches."""
    monkeypatch.chdir(tmp_path)
    kernel = KernelSource.from_mapping(
        {BASE + "01-a.md": "# A\n"}, BASE, Path("virtual/deck")
    )
    assert kernel.root.is_absolute()
    resolved = resolve_source(Path("virtual/deck"), src=kernel)
    assert resolved.entries == ["01-a.md"]
    assert assemble_resolved(resolved, src=kernel).slide_count == 1


def test_kernel_manifest_that_is_not_utf8_is_a_config_error():
    kernel = KernelSource.from_mapping(
        {BASE + "deck.toml": b'title = "\xff\xfe"\n'}, BASE, KROOT
    )
    with pytest.raises(ConfigError, match="not valid UTF-8"):
        resolve_source(KROOT, src=kernel)

"""Font Awesome resolution: off, free CDN, and verbatim self-host copy."""

from lectern import fontawesome


def _kit(tmp_path):
    """A minimal Font Awesome kit: css/all.min.css referencing ../webfonts/."""
    kit = tmp_path / "kit"
    (kit / "css").mkdir(parents=True)
    (kit / "webfonts").mkdir(parents=True)
    (kit / "css" / "all.min.css").write_text(
        "@font-face{font-family:FA;src:url(../webfonts/fa.woff2)}", encoding="utf-8"
    )
    (kit / "webfonts" / "fa.woff2").write_bytes(b"FONT")
    return kit


def test_off_returns_none(tmp_path):
    w = []
    assert fontawesome.resolve(False, tmp_path, tmp_path / "out", w) is None
    assert fontawesome.resolve("", tmp_path, tmp_path / "out", w) is None
    assert w == []


def test_true_returns_pinned_free_cdn(tmp_path):
    href = fontawesome.resolve(True, tmp_path, tmp_path / "out", [])
    assert href == fontawesome.FREE_CDN
    assert "fontawesome-free@" in href  # pinned, not "latest"


def test_local_kit_copied_verbatim(tmp_path):
    kit = _kit(tmp_path)
    out = tmp_path / "out"
    href = fontawesome.resolve(str(kit), tmp_path, out, [])
    # links the local CSS, relative
    assert href == "font-awesome/css/all.min.css"
    # the css/ + webfonts/ structure is preserved (so ../webfonts/ resolves)
    assert (out / "font-awesome" / "css" / "all.min.css").is_file()
    assert (out / "font-awesome" / "webfonts" / "fa.woff2").is_file()


def test_local_kit_relative_path_resolves_against_deck_root(tmp_path):
    _kit(tmp_path)  # at tmp_path/kit
    href = fontawesome.resolve("kit", tmp_path, tmp_path / "out", [])
    assert href == "font-awesome/css/all.min.css"


def test_local_missing_dir_warns(tmp_path):
    w = []
    out = fontawesome.resolve(str(tmp_path / "nope"), tmp_path, tmp_path / "o", w)
    assert out is None
    assert any("not found" in m for m in w)


def test_local_without_css_warns(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    w = []
    assert fontawesome.resolve(str(bare), tmp_path, tmp_path / "o", w) is None
    assert any("no css" in m for m in w)

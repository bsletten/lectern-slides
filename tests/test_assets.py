"""Asset resolution: rewrite, copy, dedupe, URL prefixing, missing warnings."""

from conftest import write

from lectern.assets import AssetResolver


def _resolver(tmp_path, asset_base=None, warnings=None):
    return AssetResolver(
        root=tmp_path,
        asset_base=asset_base,
        out_dir=tmp_path / "dist",
        warnings=warnings if warnings is not None else [],
    )


def test_relative_ref_copied_and_rewritten(tmp_path):
    write(tmp_path, "slides/pic.png", "imagedata")
    r = _resolver(tmp_path)
    out = r.rewrite("![x](pic.png)", tmp_path / "slides", "slides/s.md")
    assert "assets/pic-" in out
    assert len(r.copied) == 1
    assert r.copied[0].read_text() == "imagedata"


def test_relative_falls_back_to_asset_base_dir(tmp_path):
    # Asset lives in asset_base, referenced bare from a slide in another dir.
    write(tmp_path, "assets/bg.svg", "<svg/>")
    r = _resolver(tmp_path, asset_base="./assets")
    out = r.rewrite(
        '<section data-background-image="bg.svg">', tmp_path / "slides", "s"
    )
    assert 'data-background-image="assets/bg-' in out
    assert len(r.copied) == 1


def test_http_refs_pass_through(tmp_path):
    r = _resolver(tmp_path)
    text = '![x](https://ex.com/a.png) and <a href="#/3">link</a>'
    assert r.rewrite(text, tmp_path, "s") == text
    assert r.copied == []


def test_root_absolute_with_url_asset_base(tmp_path):
    r = _resolver(tmp_path, asset_base="https://cms.example/data")
    out = r.rewrite("![x](/img/a.png)", tmp_path, "s")
    assert "https://cms.example/data/img/a.png" in out


def test_relative_with_url_asset_base_prefixes_when_absent(tmp_path):
    r = _resolver(tmp_path, asset_base="https://cms.example/data/")
    out = r.rewrite("![x](a.png)", tmp_path, "s")
    assert "https://cms.example/data/a.png" in out


def test_dedupe_by_content_hash(tmp_path):
    write(tmp_path, "a.png", "same")
    write(tmp_path, "b.png", "same")  # identical content, different name
    r = _resolver(tmp_path)
    r.rewrite("![](a.png) ![](b.png)", tmp_path, "s")
    assert len(r.copied) == 1  # copied once, reused for the second ref


def test_missing_asset_warns_and_leaves_ref(tmp_path):
    warnings: list[str] = []
    r = _resolver(tmp_path, warnings=warnings)
    out = r.rewrite("![x](nope.png)", tmp_path / "slides", "slides/s.md")
    assert "nope.png" in out  # left as-is
    assert r.copied == []
    assert any("asset not found" in w and "slides/s.md" in w for w in warnings)

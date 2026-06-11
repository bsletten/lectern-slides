"""Theme resolution and aspect-driven token injection."""

from pathlib import Path

import pytest
from conftest import write

from lectern.errors import ConfigError
from lectern.theming import build_theme, resolve_theme_css, slide_dimensions


@pytest.mark.parametrize(
    ("aspect", "expected"),
    [
        ("16:9", (1280, 720)),
        ("4:3", (1024, 768)),
        ("1280x720", (1280, 720)),
        ("1920x1080", (1920, 1080)),
        ("3:2", (1080, 720)),  # arbitrary ratio normalized to height 720
    ],
)
def test_slide_dimensions(aspect, expected):
    assert slide_dimensions(aspect) == expected


def test_invalid_aspect_raises():
    with pytest.raises(ConfigError):
        slide_dimensions("not-an-aspect")


def test_bundled_theme_by_name(tmp_path):
    name, css = resolve_theme_css("base", tmp_path)
    assert name == "base"
    assert "--slide-w" in css  # the bundled base theme defines the token contract


def test_unknown_bundled_theme_raises(tmp_path):
    with pytest.raises(ConfigError, match="unknown theme"):
        resolve_theme_css("does-not-exist", tmp_path)


def _bundled_theme_names():
    from importlib.resources import files

    return sorted(
        p.name.removesuffix(".css")
        for p in files("lectern.themes").iterdir()
        if p.name.endswith(".css")
    )


@pytest.mark.parametrize("name", _bundled_theme_names())
def test_bundled_themes_resolve_by_name(name, tmp_path):
    resolved_name, css = resolve_theme_css(name, tmp_path)
    assert resolved_name == name
    assert "--" in css  # carries design tokens / custom properties


def test_theme_path_search_dir_resolves_bare_name(tmp_path):
    write(tmp_path, "lib/house.css", "/* HOUSE */")
    name, css = resolve_theme_css("house", tmp_path, [tmp_path / "lib"])
    assert name == "house"
    assert "HOUSE" in css


def test_theme_paths_searched_before_bundled(tmp_path):
    # A theme dir shadows a bundled name of the same stem.
    write(tmp_path, "lib/base.css", "/* SHADOW BASE */")
    _name, css = resolve_theme_css("base", tmp_path, [tmp_path / "lib"])
    assert "SHADOW BASE" in css


def test_unknown_theme_error_mentions_theme_paths(tmp_path):
    with pytest.raises(ConfigError, match="theme_paths"):
        resolve_theme_css("nope", tmp_path, [tmp_path / "lib"])


def test_resolve_theme_dirs_against_root(tmp_path):
    from lectern.theming import resolve_theme_dirs

    dirs = resolve_theme_dirs(["./local", "/abs/themes"], tmp_path)
    assert dirs == [tmp_path / "local", Path("/abs/themes")]


def test_build_theme_uses_theme_paths(tmp_path):
    write(tmp_path, "lib/house.css", ":root { --slide-w: 1px; }")
    theme = build_theme("house", "16:9", tmp_path, ["./lib"])
    assert theme.name == "house"
    assert "--slide-w" in theme.css


def test_theme_path_resolves_against_root(tmp_path):
    write(tmp_path, "themes/custom.css", ":root { --accent: #abcdef; }")
    name, css = resolve_theme_css("./themes/custom.css", tmp_path)
    assert name == "custom"
    assert "#abcdef" in css


def test_missing_theme_path_raises(tmp_path):
    with pytest.raises(ConfigError, match="theme file not found"):
        resolve_theme_css("./themes/missing.css", tmp_path)


def test_build_theme_injects_aspect_override(tmp_path):
    theme = build_theme("base", "4:3", tmp_path)
    assert (theme.width, theme.height) == (1024, 768)
    # The override comes last so the configured aspect wins over the theme default.
    assert theme.css.rstrip().endswith("--slide-w: 1024px; --slide-h: 768px; }")

"""Theme resolution and aspect-driven token injection."""

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
    with pytest.raises(ConfigError, match="unknown bundled theme"):
        resolve_theme_css("does-not-exist", tmp_path)


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

"""Three-layer config precedence and deck-root-relative path resolution."""

from pathlib import Path

from conftest import write

from lectern.config import resolve_source


def test_precedence_user_then_deck_then_cli(tmp_path, isolate_user_config):
    # Layer 3 (user config): house defaults set once globally.
    write(
        isolate_user_config,
        "lectern/config.toml",
        'theme = "house"\nrenderer = "remark"\n',
    )
    # Layer 2 (deck.toml): overrides renderer, inherits theme.
    write(tmp_path, "a.md", "# A")
    write(tmp_path, "deck.toml", 'renderer = "reveal"\nslides = ["a.md"]\n')

    rs = resolve_source(tmp_path)
    assert rs.config.theme == "house"  # inherited from user config
    assert rs.config.renderer == "reveal"  # deck beats user

    # Layer 1 (CLI flags) beats deck.
    rs_cli = resolve_source(tmp_path, cli_overrides={"renderer": "marp"})
    assert rs_cli.config.renderer == "marp"


def test_user_config_absent_falls_back_to_defaults(tmp_path):
    write(tmp_path, "a.md", "# A")
    write(tmp_path, "deck.toml", 'slides = ["a.md"]\n')
    rs = resolve_source(tmp_path)
    assert rs.config.renderer == "reveal"  # built-in default
    assert rs.config.theme == "base"


def test_nested_section_merge(tmp_path, isolate_user_config):
    write(
        isolate_user_config,
        "lectern/config.toml",
        '[reveal]\nmath = "katex"\nhighlight = true\n',
    )
    write(tmp_path, "a.md", "# A")
    write(tmp_path, "deck.toml", 'slides = ["a.md"]\n[reveal]\nhighlight = false\n')
    rs = resolve_source(tmp_path)
    # math inherited from user; highlight overridden by deck.
    assert rs.config.reveal.math == "katex"
    assert rs.config.reveal.highlight is False


def test_out_and_build_dirs_default_under_deck_root(tmp_path):
    write(tmp_path, "a.md", "# A")
    write(tmp_path, "deck.toml", 'slides = ["a.md"]\n')
    rs = resolve_source(tmp_path)
    assert rs.out_dir == tmp_path.resolve() / "dist"
    assert rs.build_dir == tmp_path.resolve() / "build"


def test_out_dir_override_relative_and_absolute(tmp_path):
    write(tmp_path, "a.md", "# A")
    write(tmp_path, "deck.toml", 'slides = ["a.md"]\n')
    rel = resolve_source(tmp_path, cli_overrides={"out_dir": "site"})
    assert rel.out_dir == tmp_path.resolve() / "site"
    absolute = resolve_source(tmp_path, cli_overrides={"out_dir": "/tmp/lectern-x"})
    assert absolute.out_dir == Path("/tmp/lectern-x")


def test_partials_from_user_config_resolve_against_each_deck_root(
    tmp_path, isolate_user_config
):
    # A global shared partials lib (absolute path) inherited by the deck.
    shared = tmp_path / "shared-lib"
    write(shared, "house.md", "house partial")
    write(isolate_user_config, "lectern/config.toml", f'partials = ["{shared}"]\n')
    write(tmp_path, "deck.toml", 'slides = ["main.md"]\n')
    write(tmp_path, "main.md", "<!-- include: house.md -->\n")
    rs = resolve_source(tmp_path)
    assert shared in rs.partial_dirs

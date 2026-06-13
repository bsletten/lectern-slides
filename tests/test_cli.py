"""End-to-end CLI behavior for assemble and check."""

from conftest import write
from typer.testing import CliRunner

from lectern.cli import app

runner = CliRunner()


def test_assemble_to_stdout(fixtures):
    result = runner.invoke(app, ["assemble", str(fixtures / "deck")])
    assert result.exit_code == 0
    assert "# Fixture Deck" in result.stdout
    assert "<!-- @from" in result.stdout


def test_assemble_to_file(tmp_path):
    write(tmp_path, "a.md", "# Hello")
    out = tmp_path / "build" / "deck.md"
    result = runner.invoke(app, ["assemble", str(tmp_path / "a.md"), "-o", str(out)])
    assert result.exit_code == 0
    assert out.read_text(encoding="utf-8").count("# Hello") == 1
    assert "assembled 1 slide" in result.stderr


def test_check_ok(fixtures):
    result = runner.invoke(app, ["check", str(fixtures / "deck")])
    assert result.exit_code == 0
    assert result.stdout.startswith("ok:")


def test_check_reports_error_with_location(tmp_path):
    write(tmp_path, "main.md", "x\n<!-- include: missing.md -->\n")
    result = runner.invoke(app, ["check", str(tmp_path / "main.md")])
    assert result.exit_code == 1
    assert "error:" in result.stderr
    assert "missing.md" in result.stderr


def test_build_writes_index_and_reports(fixtures, tmp_path):
    out = tmp_path / "site"
    result = runner.invoke(
        app, ["build", str(fixtures / "render-deck"), "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert (out / "index.html").is_file()
    assert "built 3 slide(s)" in result.stdout


def test_build_outline_writes_markdown(fixtures, tmp_path):
    result = runner.invoke(
        app,
        ["build", str(fixtures / "render-deck"), "-f", "outline", "-o", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "outline.md").is_file()
    assert "wrote outline" in result.stdout


def test_build_rejects_unsupported_format(fixtures, tmp_path):
    # reveal can't make pptx; the error should name the format and suggest marp.
    result = runner.invoke(
        app, ["build", str(fixtures / "render-deck"), "-o", str(tmp_path), "-f", "pptx"]
    )
    assert result.exit_code == 1
    assert "pptx" in result.stderr
    assert "marp" in result.stderr


def test_build_rejects_unknown_format(fixtures, tmp_path):
    result = runner.invoke(
        app, ["build", str(fixtures / "render-deck"), "-o", str(tmp_path), "-f", "xyz"]
    )
    assert result.exit_code == 1
    assert "xyz" in result.stderr


def test_config_shows_provenance(fixtures):
    result = runner.invoke(
        app, ["config", str(fixtures / "render-deck"), "--theme", "japandi"]
    )
    assert result.exit_code == 0
    assert "deck root:" in result.stdout
    assert "renderer" in result.stdout
    # The CLI override is attributed to the cli layer.
    assert "japandi" in result.stdout
    assert "(cli)" in result.stdout
    # An unset key falls back to the built-in default.
    assert "(default)" in result.stdout


def test_config_override_flags_flow_through(fixtures):
    result = runner.invoke(
        app,
        ["config", str(fixtures / "render-deck"), "--remark-compat", "--aspect", "4:3"],
    )
    assert result.exit_code == 0
    assert "remark_compat" in result.stdout
    assert "4:3" in result.stdout


def test_assemble_remark_compat_flag(tmp_path):
    write(tmp_path, "s.md", "class: center\n\n# T\n\n.accent[x] here\n")
    result = runner.invoke(app, ["assemble", str(tmp_path / "s.md"), "--remark-compat"])
    assert result.exit_code == 0
    assert "<!-- slide: .center -->" in result.stdout
    assert "[x]{.accent}" in result.stdout


def test_partial_flag_replaces_search_dirs(tmp_path):
    write(tmp_path, "lib/shared.md", "shared body")
    write(tmp_path, "main.md", "<!-- include: shared.md -->\n")
    # No partials configured; the flag supplies the search dir.
    result = runner.invoke(
        app, ["assemble", str(tmp_path / "main.md"), "--partial", str(tmp_path / "lib")]
    )
    assert result.exit_code == 0
    assert "shared body" in result.stdout


def test_watch_renderer_override_validated(fixtures):
    # -r flows into the resolved config; an unknown renderer fails fast (before
    # the server starts), which proves the override reaches config.renderer.
    result = runner.invoke(app, ["watch", str(fixtures / "render-deck"), "-r", "bogus"])
    assert result.exit_code == 1
    assert "bogus" in result.stderr


def test_watch_fails_fast_on_bad_source(tmp_path):
    # A resolution error must surface before the server starts (so the command
    # exits instead of blocking). A valid source would block on the server.
    result = runner.invoke(app, ["watch", str(tmp_path / "nope.md")])
    assert result.exit_code == 1
    assert "error:" in result.stderr


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "lectern" in result.stdout


def _xdg(tmp_path, author=None):
    """An isolated XDG_CONFIG_HOME env, optionally with a user-config author."""
    cfg = tmp_path / "xdg"
    if author is not None:
        d = cfg / "lectern"
        d.mkdir(parents=True, exist_ok=True)
        (d / "config.toml").write_text(f'author = "{author}"\n', encoding="utf-8")
    return {"XDG_CONFIG_HOME": str(cfg)}


def test_new_scaffolds_and_checks_clean(tmp_path):
    deck = tmp_path / "talk"
    result = runner.invoke(app, ["new", str(deck)], env=_xdg(tmp_path))
    assert result.exit_code == 0
    assert (deck / "deck.toml").is_file()
    assert (deck / "slides" / "00-title.md").is_file()
    assert (deck / "slides" / "10-content.md").is_file()
    # the scaffolded deck assembles cleanly
    check = runner.invoke(app, ["check", str(deck)], env=_xdg(tmp_path))
    assert check.exit_code == 0


def test_new_defaults_to_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new"], env=_xdg(tmp_path))
    assert result.exit_code == 0
    assert (tmp_path / "deck.toml").is_file()
    # title is derived from the directory name (`-`/`_` become spaces)
    expected = tmp_path.name.replace("-", " ").replace("_", " ").title()
    assert f'title    = "{expected}"' in (tmp_path / "deck.toml").read_text("utf-8")


def test_new_author_defaults_to_placeholder(tmp_path):
    deck = tmp_path / "talk"
    runner.invoke(app, ["new", str(deck)], env=_xdg(tmp_path))  # no user-config author
    assert 'author   = "Deck Author"' in (deck / "deck.toml").read_text("utf-8")


def test_new_author_inherited_from_user_config_not_written(tmp_path):
    deck = tmp_path / "talk"
    result = runner.invoke(
        app, ["new", str(deck)], env=_xdg(tmp_path, author="Ada Lovelace")
    )
    assert result.exit_code == 0
    toml = (deck / "deck.toml").read_text("utf-8")
    assert "Ada Lovelace" not in toml  # the name is never committed into the deck
    assert "inherited from your user config" in toml


def test_new_author_flag_wins(tmp_path):
    deck = tmp_path / "talk"
    runner.invoke(
        app, ["new", str(deck), "--author", "Grace H."], env=_xdg(tmp_path, author="X")
    )
    assert 'author   = "Grace H."' in (deck / "deck.toml").read_text("utf-8")


def test_new_refuses_overwrite_without_force(tmp_path):
    deck = tmp_path / "talk"
    assert runner.invoke(app, ["new", str(deck)], env=_xdg(tmp_path)).exit_code == 0
    again = runner.invoke(app, ["new", str(deck)], env=_xdg(tmp_path))
    assert again.exit_code == 1
    assert "overwrite" in again.stderr
    forced = runner.invoke(app, ["new", str(deck), "--force"], env=_xdg(tmp_path))
    assert forced.exit_code == 0


def _deck_with_dirs(tmp_path):
    """A minimal manifest deck plus a populated dist/ and build/ cache."""
    write(tmp_path, "deck.toml", 'slides = ["slides/a.md"]\n')
    write(tmp_path, "slides/a.md", "# A\n")
    write(tmp_path, "dist/index.html", "<html></html>")
    write(tmp_path, "build/.lectern-cache/master-x.pdf", "%PDF")
    return tmp_path


def test_clean_removes_out_dir_keeps_build(tmp_path):
    deck = _deck_with_dirs(tmp_path)
    result = runner.invoke(app, ["clean", str(deck), "-y"])
    assert result.exit_code == 0
    assert not (deck / "dist").exists()
    assert (deck / "build" / ".lectern-cache").exists()  # cache preserved


def test_clean_all_removes_build_too(tmp_path):
    deck = _deck_with_dirs(tmp_path)
    result = runner.invoke(app, ["clean", str(deck), "--all", "-y"])
    assert result.exit_code == 0
    assert not (deck / "dist").exists()
    assert not (deck / "build").exists()


def test_clean_dry_run_removes_nothing(tmp_path):
    deck = _deck_with_dirs(tmp_path)
    result = runner.invoke(app, ["clean", str(deck), "--all", "--dry-run"])
    assert result.exit_code == 0
    assert "would remove" in result.stdout
    assert (deck / "dist").exists() and (deck / "build").exists()


def test_clean_prompts_without_yes(tmp_path):
    deck = _deck_with_dirs(tmp_path)
    # answering "n" aborts and leaves everything in place
    result = runner.invoke(app, ["clean", str(deck)], input="n\n")
    assert result.exit_code != 0
    assert (deck / "dist").exists()


def test_clean_refuses_deck_root_as_out_dir(tmp_path):
    write(tmp_path, "deck.toml", 'out_dir = "."\nslides = ["slides/a.md"]\n')
    write(tmp_path, "slides/a.md", "# A\n")
    result = runner.invoke(app, ["clean", str(tmp_path), "-y"])
    assert result.exit_code == 0
    assert "is the deck root" in result.stderr
    assert (tmp_path / "slides" / "a.md").exists()  # source untouched


def test_clean_refuses_source_dir_as_out_dir(tmp_path):
    write(tmp_path, "deck.toml", 'out_dir = "slides"\nslides = ["slides/a.md"]\n')
    write(tmp_path, "slides/a.md", "# A\n")
    result = runner.invoke(app, ["clean", str(tmp_path), "-y"])
    assert result.exit_code == 0
    assert "source/input directory" in result.stderr
    assert (tmp_path / "slides" / "a.md").exists()

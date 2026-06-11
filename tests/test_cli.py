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

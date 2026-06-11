"""Entry resolution: manifest / directory / single-file modes."""

from pathlib import Path

import pytest
from conftest import write

from lectern.config import resolve_source
from lectern.errors import ConfigError


def test_manifest_mode_uses_slides_list(tmp_path):
    write(tmp_path, "a.md", "a")
    write(tmp_path, "b.md", "b")
    write(tmp_path, "deck.toml", 'slides = ["b.md", "a.md"]\n')
    rs = resolve_source(tmp_path)
    assert rs.mode == "manifest"
    assert rs.entries == ["b.md", "a.md"]  # explicit order, not lexical
    assert rs.root == tmp_path


def test_directory_mode_without_slides(tmp_path):
    write(tmp_path, "20-b.md", "b")
    write(tmp_path, "10-a.md", "a")
    write(tmp_path, "deck.toml", 'title = "no slides list"\n')
    rs = resolve_source(tmp_path)
    assert rs.mode == "directory"
    assert rs.entries == ["10-a.md", "20-b.md"]  # lexical


def test_directory_mode_without_manifest(tmp_path):
    write(tmp_path, "10-a.md", "a")
    rs = resolve_source(tmp_path)
    assert rs.mode == "directory"
    assert rs.entries == ["10-a.md"]


def test_single_file_mode(tmp_path):
    f = write(tmp_path, "solo.md", "x")
    rs = resolve_source(f)
    assert rs.mode == "single"
    assert rs.entries == ["solo.md"]
    assert rs.root == tmp_path


def test_toml_path_as_source(tmp_path):
    write(tmp_path, "a.md", "a")
    manifest = write(tmp_path, "deck.toml", 'slides = ["a.md"]\n')
    rs = resolve_source(manifest)
    assert rs.entries == ["a.md"]
    assert rs.root == tmp_path


def test_partial_dirs_resolved_against_root(tmp_path):
    write(tmp_path, "deck.toml", 'partials = ["../shared", "./_lib"]\nslides = []\n')
    write(tmp_path, "x.md", "x")
    # slides=[] is falsy -> directory mode; partials still resolve.
    rs = resolve_source(tmp_path)
    assert rs.partial_dirs[0] == tmp_path / ".." / "shared"
    assert rs.partial_dirs[1] == tmp_path / "_lib"


def test_theme_dirs_resolved_against_root(tmp_path):
    write(
        tmp_path, "deck.toml", 'theme_paths = ["./_themes", "/abs/lib"]\nslides = []\n'
    )
    write(tmp_path, "x.md", "x")
    rs = resolve_source(tmp_path)
    assert rs.theme_dirs[0] == tmp_path / "_themes"
    assert rs.theme_dirs[1] == Path("/abs/lib")


def test_unknown_source_type_errors(tmp_path):
    bogus = write(tmp_path, "thing.txt", "nope")
    with pytest.raises(ConfigError):
        resolve_source(bogus)


def test_config_override(tmp_path):
    write(tmp_path, "a.md", "a")
    other = write(tmp_path, "custom.toml", 'slides = ["a.md"]\n')
    rs = resolve_source(tmp_path, config_override=other)
    assert rs.entries == ["a.md"]

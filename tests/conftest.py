from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolate_user_config(tmp_path_factory, monkeypatch):
    """Point XDG_CONFIG_HOME at an empty dir so the dev's real user config

    never leaks into tests. Tests that exercise layering write their own
    lectern/config.toml under this directory.
    """
    cfg_home = tmp_path_factory.mktemp("xdg-config")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg_home))
    return cfg_home


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def write(base: Path, name: str, content: str) -> Path:
    """Write *content* to base/name, creating parents. Returns the path."""
    path = base / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path

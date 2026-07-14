import pytest

from linuxshot.config import Config


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Point every XDG path at a temp dir and reset the config singleton
    so tests can't touch (or depend on) the real user environment.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    Config._instance = None
    yield
    Config._instance = None

import os

import pytest

import linuxshot.app as app_mod
from linuxshot.app import App
from linuxshot.capture import CaptureMode, CaptureResult
from linuxshot.history import History


class QuietModule:
    """Stands in for clipboard/notify so tests never touch the session."""

    def __getattr__(self, name):
        return lambda *a, **kw: True


@pytest.fixture(autouse=True)
def quiet_side_effects(monkeypatch):
    monkeypatch.setattr(app_mod, "clipboard", QuietModule())
    monkeypatch.setattr(app_mod, "notify", QuietModule())


@pytest.fixture
def app_with_capture(tmp_path, monkeypatch):
    """An App whose capture engine writes a predictable file."""
    app = App()
    shot = tmp_path / "shot.png"

    def fake_capture(mode):
        shot.write_bytes(b"png data")
        return CaptureResult(str(shot), mode)

    monkeypatch.setattr(app.capture_engine, "capture", fake_capture)
    return app, str(shot)


def test_capture_without_editor(app_with_capture):
    app, shot = app_with_capture
    assert app.run_capture(CaptureMode.REGION) is True
    entries = History().get_entries()
    assert len(entries) == 1
    assert entries[0].filepath == shot
    assert entries[0].uploaded is False


def test_editor_discard_deletes_file_and_skips_history(app_with_capture):
    app, shot = app_with_capture
    assert app.run_capture(CaptureMode.REGION, editor=lambda p: "discard") is False
    assert not os.path.exists(shot)
    assert History().count == 0


def test_editor_rewrite_updates_filesize(app_with_capture):
    app, shot = app_with_capture

    def editor(path):
        with open(path, "wb") as f:
            f.write(b"a much longer annotated image payload")
        return "done"

    assert app.run_capture(CaptureMode.REGION, editor=editor) is True
    entry = History().get_entries()[0]
    assert entry.filesize == len(b"a much longer annotated image payload")


def test_editor_skip_keeps_original(app_with_capture):
    app, shot = app_with_capture
    assert app.run_capture(CaptureMode.REGION, editor=lambda p: "skip") is True
    assert os.path.exists(shot)
    assert History().count == 1


def test_cancelled_capture_never_reaches_editor(app_with_capture, monkeypatch):
    app, _ = app_with_capture
    monkeypatch.setattr(app.capture_engine, "capture", lambda mode: None)
    called = []
    assert app.run_capture(CaptureMode.REGION, editor=called.append) is False
    assert called == []

import subprocess

import pytest

import linuxshot.colorpick as colorpick_mod
import linuxshot.ocr as ocr_mod
from linuxshot.colorpick import _rgb_to_hex, pick_color
from linuxshot.ocr import OcrError, extract_text


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def test_ocr_requires_tesseract(monkeypatch):
    monkeypatch.setattr(ocr_mod, "has_command", lambda cmd: False)
    with pytest.raises(OcrError, match="tesseract is not installed"):
        extract_text("/tmp/x.png")


def test_ocr_extracts_and_strips(monkeypatch):
    monkeypatch.setattr(ocr_mod, "has_command", lambda cmd: True)
    monkeypatch.setattr(ocr_mod, "run_cmd",
                        lambda cmd: completed(stdout="  hello world\n\n"))
    assert extract_text("/tmp/x.png") == "hello world"


def test_ocr_passes_language(monkeypatch):
    monkeypatch.setattr(ocr_mod, "has_command", lambda cmd: True)
    seen = {}

    def fake_run(cmd):
        seen["cmd"] = cmd
        return completed(stdout="ok")

    monkeypatch.setattr(ocr_mod, "run_cmd", fake_run)
    extract_text("/tmp/x.png", language="deu")
    assert seen["cmd"][-2:] == ["-l", "deu"]


def test_ocr_missing_language_gives_install_hint(monkeypatch):
    monkeypatch.setattr(ocr_mod, "has_command", lambda cmd: True)

    def fake_run(cmd):
        if "--list-langs" in cmd:
            return completed(stdout="List of available languages (2):\nafr\nosd\n")
        return completed(stderr="Failed loading language 'eng'\n"
                                "Could not initialize tesseract.\n", returncode=1)

    monkeypatch.setattr(ocr_mod, "run_cmd", fake_run)
    with pytest.raises(OcrError) as err:
        extract_text("/tmp/x.png")
    assert "installed: afr" in str(err.value)
    assert "tesseract-data-eng" in str(err.value)


def test_ocr_surfaces_tesseract_error(monkeypatch):
    monkeypatch.setattr(ocr_mod, "has_command", lambda cmd: True)
    monkeypatch.setattr(ocr_mod, "run_cmd",
                        lambda cmd: completed(stderr="Error: bad image\n", returncode=1))
    with pytest.raises(OcrError, match="bad image"):
        extract_text("/tmp/x.png")


def test_rgb_to_hex():
    assert _rgb_to_hex(1.0, 0.0, 0.0) == "#ff0000"
    assert _rgb_to_hex(0.0, 0.5, 1.0) == "#0080ff"
    assert _rgb_to_hex(1.2, -0.1, 0.0) == "#ff0000"  # clamped


def test_pick_color_falls_back_to_hyprpicker(monkeypatch):
    monkeypatch.setattr(colorpick_mod, "_pick_via_portal", lambda timeout: None)
    monkeypatch.setattr("linuxshot.utils.has_command", lambda cmd: cmd == "hyprpicker")
    monkeypatch.setattr("linuxshot.utils.run_cmd",
                        lambda cmd, **kw: completed(stdout="#12ab34\n"))
    assert pick_color() == "#12ab34"


def test_pick_color_none_when_nothing_available(monkeypatch):
    monkeypatch.setattr(colorpick_mod, "_pick_via_portal", lambda timeout: None)
    monkeypatch.setattr("linuxshot.utils.has_command", lambda cmd: False)
    assert pick_color() is None

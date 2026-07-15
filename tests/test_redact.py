import subprocess

import pytest

import linuxshot.redact as redact_mod
from linuxshot.ocr import OcrError
from linuxshot.redact import _scan_tsv, classify, find_sensitive_regions


@pytest.mark.parametrize("word,label", [
    ("user@example.com", "email"),
    ("lord.max+test@gmail.com", "email"),
    ("192.168.1.10", "ip address"),
    ("10.0.0.1:8080", "ip address"),
    ("API_KEY=abc123", "credential"),
    ("password=hunter2", "credential"),
    ("token=deadbeef", "credential"),
    ("sk-live-abcdef1234567890", "api key"),
    ("ghp_16C7e42F292c6912E7710c838347Ae178B4a", "api key"),
    ("AKIAIOSFODNN7EXAMPLE", "api key"),
    ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "api key"),
    ("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6", "token"),
])
def test_classify_flags_secrets(word, label):
    assert classify(word) == label


@pytest.mark.parametrize("word", [
    "hello",
    "the",
    "screenshot",
    "LinuxShot_2026-07-14_21-42-18.png",  # filename with date
    "2026-07-14T21:42:18.000000",         # timestamp
    "/usr/local/bin/linuxshot",           # path, no digits enough
    "user@host:~$",                       # shell prompt, not an email
    "installation",
])
def test_classify_ignores_ordinary_words(word):
    assert classify(word) is None


def make_tsv(rows):
    header = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
              "\tleft\ttop\twidth\theight\tconf\ttext")
    return header + "\n" + "\n".join(rows)


def test_scan_tsv_extracts_boxes():
    tsv = make_tsv([
        "5\t1\t1\t1\t1\t1\t40\t80\t300\t22\t96.5\tsk-live-abcdef1234567890",
        "5\t1\t1\t1\t2\t1\t40\t120\t200\t22\t91.0\thello",
        "5\t1\t1\t1\t3\t1\t40\t160\t250\t22\t88.2\tuser@example.com",
    ])
    regions = _scan_tsv(tsv)
    assert len(regions) == 2
    assert regions[0].label == "api key"
    assert (regions[0].x, regions[0].y) == (40, 80)
    assert regions[1].label == "email"


def test_scan_tsv_respects_confidence():
    tsv = make_tsv([
        "5\t1\t1\t1\t1\t1\t40\t80\t300\t22\t12.0\tsk-live-abcdef1234567890",
    ])
    assert _scan_tsv(tsv) == []


def test_scan_tsv_skips_non_word_rows():
    tsv = make_tsv([
        "4\t1\t1\t1\t1\t0\t40\t80\t300\t22\t-1\t",
        "5\t1\t1\t1\t1\t1\t40\t80\t300\t22\t95.0\tuser@example.com",
    ])
    assert len(_scan_tsv(tsv)) == 1


def test_find_regions_requires_tesseract(monkeypatch):
    monkeypatch.setattr(redact_mod, "has_command", lambda cmd: False)
    with pytest.raises(OcrError, match="tesseract"):
        find_sensitive_regions("/tmp/x.png")


def test_find_regions_passes_language(monkeypatch):
    monkeypatch.setattr(redact_mod, "has_command", lambda cmd: True)
    seen = {}

    def fake_run(cmd):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=make_tsv([]), stderr="")

    monkeypatch.setattr(redact_mod, "run_cmd", fake_run)
    find_sensitive_regions("/tmp/x.png", language="eng")
    assert "-l" in seen["cmd"] and "tsv" in seen["cmd"]

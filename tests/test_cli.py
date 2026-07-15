import json

from linuxshot.__main__ import build_parser, cmd_config, cmd_history
from linuxshot.config import Config
from linuxshot.history import History


def parse(*argv):
    return build_parser().parse_args(argv)


def test_parser_accepts_all_commands():
    for cmd in ("region", "fullscreen", "window", "upload-last", "history",
                "config", "tray", "gui", "setup", "update", "check",
                "ocr", "pick-color", "pin"):
        args = parse(cmd)
        assert args.command == cmd

    args = parse("upload", "/tmp/x.png")
    assert args.file == "/tmp/x.png"

    args = parse("edit", "/tmp/x.png")
    assert args.file == "/tmp/x.png"

    assert parse("pin").file == ""  # defaults to most recent capture


def test_config_set_parses_json_values(capsys):
    assert cmd_config(parse("config", "--set", "auto_upload", "true")) == 0
    assert Config()["auto_upload"] is True

    assert cmd_config(parse("config", "--set", "capture_delay", "3")) == 0
    assert Config()["capture_delay"] == 3

    assert cmd_config(parse("config", "--set", "image_format", "jpg")) == 0
    assert Config()["image_format"] == "jpg"


def test_config_set_rejects_unknown_key(capsys):
    assert cmd_config(parse("config", "--set", "not_a_key", "1")) == 1
    assert "Unknown key" in capsys.readouterr().err


def test_config_get(capsys):
    assert cmd_config(parse("config", "--get", "image_format")) == 0
    assert "png" in capsys.readouterr().out

    assert cmd_config(parse("config", "--get", "bogus")) == 1


def test_history_output(capsys):
    History().add("/tmp/a.png", "region", filesize=2048)

    assert cmd_history(parse("history")) == 0
    out = capsys.readouterr().out
    assert "/tmp/a.png" in out
    assert "2 KB" in out


def test_history_json_output(capsys):
    History().add("/tmp/a.png", "region")

    assert cmd_history(parse("history", "--json")) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["filepath"] == "/tmp/a.png"


def test_history_clear(capsys):
    History().add("/tmp/a.png", "region")
    assert cmd_history(parse("history", "--clear")) == 0
    assert History().count == 0

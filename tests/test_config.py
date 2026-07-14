import json
import os
import stat

from linuxshot.config import DEFAULTS, Config


def test_defaults_when_no_file():
    config = Config()
    assert config["image_format"] == "png"
    assert config["auto_upload"] is False
    assert config.data == DEFAULTS


def test_set_save_load_roundtrip():
    config = Config()
    config["image_format"] = "webp"
    config["capture_delay"] = 5
    config.save()

    reloaded = Config()
    assert reloaded["image_format"] == "webp"
    assert reloaded["capture_delay"] == 5
    # untouched keys still fall back to defaults
    assert reloaded["jpg_quality"] == DEFAULTS["jpg_quality"]


def test_saved_file_is_private():
    config = Config()
    config["imgbb_api_key"] = "secret"
    config.save()
    mode = stat.S_IMODE(os.stat(config.path).st_mode)
    assert mode == 0o600


def test_unknown_keys_from_disk_are_preserved():
    config = Config()
    config.save()
    with open(config.path) as f:
        data = json.load(f)
    data["future_option"] = 42
    with open(config.path, "w") as f:
        json.dump(data, f)

    reloaded = Config()
    reloaded.save()
    with open(reloaded.path) as f:
        assert json.load(f)["future_option"] == 42


def test_corrupt_file_falls_back_to_defaults():
    config = Config()
    with open(config.path, "w") as f:
        f.write("{not json")
    reloaded = Config()
    assert reloaded["image_format"] == DEFAULTS["image_format"]


def test_reset():
    config = Config()
    config["image_format"] = "jpg"
    config.save()
    config.reset()
    assert config["image_format"] == DEFAULTS["image_format"]
    assert Config().data == DEFAULTS


def test_is_known_key():
    config = Config()
    assert config.is_known_key("auto_upload")
    assert not config.is_known_key("no_such_key")


def test_singleton():
    assert Config.get() is Config.get()


def test_custom_screenshot_dir_created(tmp_path):
    config = Config()
    custom = tmp_path / "shots"
    config["screenshot_dir"] = str(custom)
    assert config.get_screenshot_dir() == str(custom)
    assert custom.is_dir()

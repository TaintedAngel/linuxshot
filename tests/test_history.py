from linuxshot.config import Config
from linuxshot.history import History


def test_add_and_get_newest_first():
    history = History()
    history.add("/tmp/a.png", "region", filesize=100)
    history.add("/tmp/b.png", "fullscreen", filesize=200)

    entries = history.get_entries()
    assert [e.filepath for e in entries] == ["/tmp/b.png", "/tmp/a.png"]
    assert entries[0].mode == "fullscreen"
    assert entries[0].filesize == 200


def test_limit():
    history = History()
    for i in range(5):
        history.add(f"/tmp/{i}.png", "region")
    assert len(history.get_entries(limit=3)) == 3
    assert len(history.get_entries()) == 5


def test_persistence():
    history = History()
    history.add("/tmp/a.png", "region")
    reloaded = History()
    assert reloaded.count == 1
    assert reloaded.get_entries()[0].filepath == "/tmp/a.png"


def test_update_upload_marks_latest_matching_entry():
    history = History()
    history.add("/tmp/a.png", "region")
    history.update_upload("/tmp/a.png", "https://i.ibb.co/x/a.png")

    entry = history.get_entries()[0]
    assert entry.uploaded is True
    assert entry.upload_url == "https://i.ibb.co/x/a.png"


def test_remove():
    history = History()
    first = history.add("/tmp/a.png", "region")
    history.add("/tmp/a.png", "region")

    history.remove("/tmp/a.png", first.timestamp)
    assert history.count == 1

    history.remove("/tmp/a.png")
    assert history.count == 0


def test_clear():
    history = History()
    history.add("/tmp/a.png", "region")
    history.clear()
    assert history.count == 0
    assert History().count == 0


def test_trims_to_max_entries():
    config = Config.get()
    config["max_history_entries"] = 3
    config.save()

    history = History()
    for i in range(10):
        history.add(f"/tmp/{i}.png", "region")

    assert history.count == 3
    assert history.get_entries()[0].filepath == "/tmp/9.png"


def test_loads_legacy_entries_with_extra_fields(tmp_path):
    history = History()
    import json
    with open(history.path, "w") as f:
        json.dump([{
            "filepath": "/tmp/old.png",
            "timestamp": "2026-01-01T00:00:00",
            "mode": "region",
            "delete_hash": "abc",  # written by 1.x
        }], f)

    reloaded = History()
    assert reloaded.count == 1
    assert reloaded.get_entries()[0].filepath == "/tmp/old.png"

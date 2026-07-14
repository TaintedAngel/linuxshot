
import pytest

import linuxshot.upload as upload_mod
from linuxshot.config import Config
from linuxshot.upload import UploadError, upload


class FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def image_file(tmp_path):
    path = tmp_path / "shot.png"
    path.write_bytes(b"\x89PNG fake image data")
    return str(path)


def set_api_key(key: str) -> None:
    config = Config.get()
    config["imgbb_api_key"] = key
    config.save()


def test_missing_file_raises():
    set_api_key("k")
    with pytest.raises(UploadError, match="File not found"):
        upload("/nonexistent/shot.png")


def test_missing_api_key_raises(image_file):
    with pytest.raises(UploadError, match="API key"):
        upload(image_file)


def test_successful_upload(image_file, monkeypatch):
    set_api_key("k")
    captured = {}

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return FakeResponse(200, {"data": {
            "url": "https://i.ibb.co/abc/shot.png",
            "url_viewer": "https://ibb.co/abc",
        }})

    monkeypatch.setattr(upload_mod.requests, "post", fake_post)

    result = upload(image_file)
    assert result.url == "https://i.ibb.co/abc/shot.png"
    assert result.page_url == "https://ibb.co/abc"
    assert result.service == "imgbb"
    assert captured["url"] == upload_mod.IMGBB_API_URL
    assert captured["data"]["key"] == "k"
    # payload must be valid base64 of the file
    import base64
    assert base64.b64decode(captured["data"]["image"]).startswith(b"\x89PNG")


def test_api_error_message_surfaced(image_file, monkeypatch):
    set_api_key("bad")
    monkeypatch.setattr(
        upload_mod.requests, "post",
        lambda *a, **kw: FakeResponse(400, {"error": {"message": "Invalid API key"}}),
    )
    with pytest.raises(UploadError, match="Invalid API key"):
        upload(image_file)


def test_http_error_without_json_body(image_file, monkeypatch):
    set_api_key("k")

    class BrokenResponse(FakeResponse):
        def json(self):
            raise ValueError("no json")

    monkeypatch.setattr(
        upload_mod.requests, "post",
        lambda *a, **kw: BrokenResponse(500, {}),
    )
    with pytest.raises(UploadError, match="HTTP 500"):
        upload(image_file)


def test_malformed_success_body(image_file, monkeypatch):
    set_api_key("k")
    monkeypatch.setattr(
        upload_mod.requests, "post",
        lambda *a, **kw: FakeResponse(200, {"data": {}}),
    )
    with pytest.raises(UploadError, match="Unexpected ImgBB response"):
        upload(image_file)


def test_connection_error(image_file, monkeypatch):
    set_api_key("k")

    def fail(*a, **kw):
        raise upload_mod.requests.ConnectionError()

    monkeypatch.setattr(upload_mod.requests, "post", fail)
    with pytest.raises(UploadError, match="connection"):
        upload(image_file)

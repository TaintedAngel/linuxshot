import base64

import pytest

import linuxshot.upload as upload_mod
from linuxshot.config import Config
from linuxshot.upload import UPLOADERS, UploadError, _dig, upload


class FakeResponse:
    def __init__(self, status_code=200, body=None, text="", headers=None):
        self.status_code = status_code
        self._body = body
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture
def image_file(tmp_path):
    path = tmp_path / "shot.png"
    path.write_bytes(b"\x89PNG fake image data")
    return str(path)


def configure(**values):
    config = Config.get()
    for key, value in values.items():
        config[key] = value
    config.save()


def stub_post(monkeypatch, response, captured=None):
    def fake_post(url, timeout=None, **kwargs):
        if captured is not None:
            captured["url"] = url
            captured.update(kwargs)
        return response
    monkeypatch.setattr(upload_mod, "_post", fake_post)


def test_missing_file_raises():
    configure(imgbb_api_key="k")
    with pytest.raises(UploadError, match="File not found"):
        upload("/nonexistent/shot.png")


def test_unknown_service_raises(image_file):
    with pytest.raises(UploadError, match="Unknown upload service"):
        upload(image_file, service="nope")


def test_default_service_comes_from_config(image_file, monkeypatch):
    configure(upload_service="0x0")
    stub_post(monkeypatch, FakeResponse(text="https://0x0.st/abc.png\n"))
    assert upload(image_file).service == "0x0"


def test_imgbb_upload(image_file, monkeypatch):
    configure(imgbb_api_key="k")
    captured = {}
    stub_post(monkeypatch, FakeResponse(body={"data": {
        "url": "https://i.ibb.co/abc/shot.png",
        "url_viewer": "https://ibb.co/abc",
        "delete_url": "https://ibb.co/abc/dodelete",
    }}), captured)

    result = upload(image_file, service="imgbb")
    assert result.url == "https://i.ibb.co/abc/shot.png"
    assert result.delete_url == "https://ibb.co/abc/dodelete"
    assert base64.b64decode(captured["data"]["image"]).startswith(b"\x89PNG")


def test_imgbb_requires_key(image_file):
    with pytest.raises(UploadError, match="API key"):
        upload(image_file, service="imgbb")


def test_imgbb_error_message(image_file, monkeypatch):
    configure(imgbb_api_key="bad")
    stub_post(monkeypatch, FakeResponse(
        status_code=400, body={"error": {"message": "Invalid API key"}}))
    with pytest.raises(UploadError, match="Invalid API key"):
        upload(image_file, service="imgbb")


def test_imgur_upload(image_file, monkeypatch):
    configure(imgur_client_id="cid")
    captured = {}
    stub_post(monkeypatch, FakeResponse(body={"data": {
        "link": "https://i.imgur.com/abc.png",
        "deletehash": "xyz",
    }}), captured)

    result = upload(image_file, service="imgur")
    assert result.url == "https://i.imgur.com/abc.png"
    assert result.delete_url == "https://imgur.com/delete/xyz"
    assert captured["headers"]["Authorization"] == "Client-ID cid"


def test_imgur_requires_client_id(image_file):
    with pytest.raises(UploadError, match="client ID"):
        upload(image_file, service="imgur")


def test_catbox_upload(image_file, monkeypatch):
    stub_post(monkeypatch, FakeResponse(text="https://files.catbox.moe/abc.png"))
    result = upload(image_file, service="catbox")
    assert result.url == "https://files.catbox.moe/abc.png"


def test_catbox_error_text_surfaced(image_file, monkeypatch):
    stub_post(monkeypatch, FakeResponse(status_code=412, text="Wrong reqtype"))
    with pytest.raises(UploadError, match="Wrong reqtype"):
        upload(image_file, service="catbox")


def test_0x0_upload_with_token(image_file, monkeypatch):
    stub_post(monkeypatch, FakeResponse(
        text="https://0x0.st/abc.png\n", headers={"X-Token": "tok"}))
    result = upload(image_file, service="0x0")
    assert result.url == "https://0x0.st/abc.png"
    assert "tok" in result.delete_url


def test_custom_uploader_json(image_file, monkeypatch):
    configure(custom_uploader={
        "request_url": "https://host/api/upload",
        "file_form_name": "upload",
        "headers": {"Authorization": "tok"},
        "response_type": "json",
        "url_key": "files.0.url",
        "delete_url_key": "files.0.delete",
    })
    captured = {}
    stub_post(monkeypatch, FakeResponse(body={"files": [
        {"url": "https://host/i/1.png", "delete": "https://host/d/1"},
    ]}), captured)

    result = upload(image_file, service="custom")
    assert result.url == "https://host/i/1.png"
    assert result.delete_url == "https://host/d/1"
    assert "upload" in captured["files"]
    assert captured["headers"]["Authorization"] == "tok"


def test_custom_uploader_text(image_file, monkeypatch):
    configure(custom_uploader={"request_url": "https://host/up", "response_type": "text"})
    stub_post(monkeypatch, FakeResponse(text="https://host/i/1.png\n"))
    assert upload(image_file, service="custom").url == "https://host/i/1.png"


def test_custom_uploader_unconfigured(image_file):
    with pytest.raises(UploadError, match="No custom uploader"):
        upload(image_file, service="custom")


def test_custom_uploader_missing_url_key(image_file, monkeypatch):
    configure(custom_uploader={
        "request_url": "https://host/up", "response_type": "json", "url_key": "nope",
    })
    stub_post(monkeypatch, FakeResponse(body={"other": 1}))
    with pytest.raises(UploadError, match="No URL"):
        upload(image_file, service="custom")


def test_all_uploaders_registered():
    assert set(UPLOADERS) == {"imgbb", "imgur", "catbox", "0x0", "custom"}


def test_dig():
    data = {"files": [{"url": "u"}], "a": {"b": "c"}}
    assert _dig(data, "files.0.url") == "u"
    assert _dig(data, "a.b") == "c"
    assert _dig(data, "a.missing") is None
    assert _dig(data, "files.9.url") is None

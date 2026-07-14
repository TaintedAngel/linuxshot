"""Image uploads to a configurable destination.

Each uploader is a small class with an `upload(filepath)` method; the
active one is chosen by the `upload_service` config key. The custom
uploader covers self-hosted services (Zipline, Chibisafe, ...) by
letting the user describe the HTTP request in config.
"""

import os
from dataclasses import dataclass

import requests

from .config import Config

UPLOAD_TIMEOUT = 60


class UploadError(Exception):
    pass


@dataclass
class UploadResult:
    url: str             # direct image link
    page_url: str = ""   # viewer page, when the service has one
    delete_url: str = "" # link or endpoint that removes the upload
    service: str = ""


def _read_file(filepath: str) -> bytes:
    if not os.path.exists(filepath):
        raise UploadError(f"File not found: {filepath}")
    try:
        with open(filepath, "rb") as f:
            return f.read()
    except OSError as e:
        raise UploadError(f"Could not read file: {e}") from e


def _post(url: str, **kwargs) -> requests.Response:
    try:
        return requests.post(url, timeout=UPLOAD_TIMEOUT, **kwargs)
    except requests.ConnectionError as e:
        raise UploadError("Could not reach the upload server. Check your connection.") from e
    except requests.Timeout as e:
        raise UploadError("Upload timed out.") from e
    except requests.RequestException as e:
        raise UploadError(f"Upload failed: {e}") from e


class ImgbbUploader:
    name = "imgbb"
    API_URL = "https://api.imgbb.com/1/upload"

    def upload(self, filepath: str) -> UploadResult:
        api_key = Config.get()["imgbb_api_key"]
        if not api_key:
            raise UploadError(
                "No ImgBB API key configured.\n"
                "Get one at https://api.imgbb.com/ then run:\n"
                "  linuxshot config --set imgbb_api_key YOUR_KEY"
            )
        import base64
        payload = base64.b64encode(_read_file(filepath)).decode("ascii")
        response = _post(self.API_URL, data={"key": api_key, "image": payload})
        if response.status_code != 200:
            raise UploadError(f"ImgBB upload failed: {_api_error(response)}")
        try:
            data = response.json()["data"]
            return UploadResult(
                url=data["url"],
                page_url=data.get("url_viewer", ""),
                delete_url=data.get("delete_url", ""),
                service=self.name,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise UploadError(f"Unexpected ImgBB response: {e}") from e


class ImgurUploader:
    name = "imgur"
    API_URL = "https://api.imgur.com/3/image"

    def upload(self, filepath: str) -> UploadResult:
        client_id = Config.get()["imgur_client_id"]
        if not client_id:
            raise UploadError(
                "No Imgur client ID configured.\n"
                "Register an application at https://api.imgur.com/oauth2/addclient\n"
                "then run: linuxshot config --set imgur_client_id YOUR_ID"
            )
        response = _post(
            self.API_URL,
            headers={"Authorization": f"Client-ID {client_id}"},
            files={"image": _read_file(filepath)},
        )
        if response.status_code != 200:
            raise UploadError(f"Imgur upload failed: {_api_error(response)}")
        try:
            data = response.json()["data"]
            delete_hash = data.get("deletehash", "")
            return UploadResult(
                url=data["link"],
                delete_url=f"https://imgur.com/delete/{delete_hash}" if delete_hash else "",
                service=self.name,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise UploadError(f"Unexpected Imgur response: {e}") from e


class CatboxUploader:
    name = "catbox"
    API_URL = "https://catbox.moe/user/api.php"

    def upload(self, filepath: str) -> UploadResult:
        data = {"reqtype": "fileupload"}
        userhash = Config.get()["catbox_userhash"]
        if userhash:
            data["userhash"] = userhash
        response = _post(
            self.API_URL,
            data=data,
            files={"fileToUpload": (os.path.basename(filepath), _read_file(filepath))},
        )
        url = response.text.strip()
        if response.status_code != 200 or not url.startswith("http"):
            raise UploadError(f"catbox upload failed: {url or response.status_code}")
        return UploadResult(url=url, service=self.name)


class NullPointerUploader:
    name = "0x0"
    API_URL = "https://0x0.st"

    def upload(self, filepath: str) -> UploadResult:
        response = _post(
            self.API_URL,
            files={"file": (os.path.basename(filepath), _read_file(filepath))},
            headers={"User-Agent": "linuxshot"},
        )
        url = response.text.strip()
        if response.status_code != 200 or not url.startswith("http"):
            raise UploadError(f"0x0.st upload failed: {url or response.status_code}")
        # The management token allows deletion: curl -F token=... -F delete= <url>
        token = response.headers.get("X-Token", "")
        return UploadResult(
            url=url,
            delete_url=f"{url}#token={token}" if token else "",
            service=self.name,
        )


class CustomUploader:
    """User-defined HTTP uploader, configured as JSON under
    `custom_uploader`:

        {
          "request_url": "https://host/api/upload",
          "file_form_name": "file",
          "headers": {"Authorization": "..."},
          "response_type": "json",       # or "text"
          "url_key": "files.0.url",      # dot path into the JSON body
          "delete_url_key": ""           # optional dot path
        }
    """

    name = "custom"

    def upload(self, filepath: str) -> UploadResult:
        spec = Config.get()["custom_uploader"]
        if not isinstance(spec, dict) or not spec.get("request_url"):
            raise UploadError(
                "No custom uploader configured. See the settings page or the\n"
                "custom_uploader config key for the expected format."
            )
        response = _post(
            spec["request_url"],
            headers=spec.get("headers") or {},
            files={
                spec.get("file_form_name", "file"):
                    (os.path.basename(filepath), _read_file(filepath))
            },
        )
        if response.status_code not in (200, 201):
            raise UploadError(f"Custom upload failed: HTTP {response.status_code}")

        if spec.get("response_type", "text") == "text":
            url = response.text.strip()
            if not url.startswith("http"):
                raise UploadError(f"Custom uploader returned no URL: {url[:200]}")
            return UploadResult(url=url, service=self.name)

        try:
            body = response.json()
        except ValueError as e:
            raise UploadError("Custom uploader response is not JSON.") from e
        url = _dig(body, spec.get("url_key", "url"))
        if not isinstance(url, str) or not url:
            raise UploadError(f"No URL at '{spec.get('url_key')}' in response.")
        delete_url = _dig(body, spec["delete_url_key"]) if spec.get("delete_url_key") else ""
        return UploadResult(
            url=url,
            delete_url=delete_url if isinstance(delete_url, str) else "",
            service=self.name,
        )


UPLOADERS = {
    cls.name: cls for cls in
    (ImgbbUploader, ImgurUploader, CatboxUploader, NullPointerUploader, CustomUploader)
}


def upload(filepath: str, service: str | None = None) -> UploadResult:
    """Upload with the given service, or the configured default."""
    name = service or Config.get()["upload_service"] or "imgbb"
    uploader = UPLOADERS.get(name)
    if uploader is None:
        raise UploadError(
            f"Unknown upload service '{name}'. "
            f"Choose one of: {', '.join(sorted(UPLOADERS))}"
        )
    return uploader().upload(filepath)


def _api_error(response: requests.Response) -> str:
    try:
        body = response.json()
        for path in ("error.message", "data.error"):
            message = _dig(body, path)
            if isinstance(message, str) and message:
                return message
    except ValueError:
        pass
    return f"HTTP {response.status_code}"


def _dig(data, dot_path: str):
    """Follow a dot path through dicts and lists: 'files.0.url'."""
    current = data
    for part in dot_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current

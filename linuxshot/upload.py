"""Image uploads via ImgBB (https://api.imgbb.com/).

ImgBB serves direct i.ibb.co links that embed cleanly in chat apps and
forums, which is why it's the default (and currently only) destination.
"""

import base64
import os
from dataclasses import dataclass

import requests

from .config import Config

IMGBB_API_URL = "https://api.imgbb.com/1/upload"
UPLOAD_TIMEOUT = 60


class UploadError(Exception):
    pass


@dataclass
class UploadResult:
    url: str        # direct image link
    page_url: str   # viewer page
    service: str = "imgbb"


def upload(filepath: str) -> UploadResult:
    if not os.path.exists(filepath):
        raise UploadError(f"File not found: {filepath}")

    api_key = Config.get()["imgbb_api_key"]
    if not api_key:
        raise UploadError(
            "No ImgBB API key configured.\n"
            "Get one at https://api.imgbb.com/ then run:\n"
            "  linuxshot config --set imgbb_api_key YOUR_KEY"
        )

    try:
        with open(filepath, "rb") as f:
            payload = base64.b64encode(f.read()).decode("ascii")
    except OSError as e:
        raise UploadError(f"Could not read file: {e}") from e

    try:
        response = requests.post(
            IMGBB_API_URL,
            data={"key": api_key, "image": payload},
            timeout=UPLOAD_TIMEOUT,
        )
    except requests.ConnectionError as e:
        raise UploadError("Could not reach ImgBB. Check your connection.") from e
    except requests.Timeout as e:
        raise UploadError("Upload timed out.") from e
    except requests.RequestException as e:
        raise UploadError(f"Upload failed: {e}") from e

    if response.status_code != 200:
        raise UploadError(f"ImgBB upload failed: {_error_message(response)}")

    try:
        data = response.json()["data"]
        return UploadResult(url=data["url"], page_url=data.get("url_viewer", data["url"]))
    except (KeyError, TypeError, ValueError) as e:
        raise UploadError(f"Unexpected ImgBB response: {e}") from e


def _error_message(response: requests.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except (KeyError, TypeError, ValueError):
        return f"HTTP {response.status_code}"

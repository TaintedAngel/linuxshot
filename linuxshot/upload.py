"""Image upload module for LinuxShot.

Uses ImgBB (https://api.imgbb.com/) for image hosting.
Links are direct (i.ibb.co) and work everywhere.
"""

import base64
import os
from dataclasses import dataclass

import requests

from .config import Config

IMGBB_API_URL = "https://api.imgbb.com/1/upload"


@dataclass
class UploadResult:
    """Result of an upload operation."""
    url: str
    delete_hash: str
    page_url: str
    service: str


class UploadError(Exception):
    """Raised when upload fails."""
    pass


def upload_to_imgbb(filepath: str) -> UploadResult:
    """Upload an image to ImgBB."""
    if not os.path.exists(filepath):
        raise UploadError(f"File not found: {filepath}")

    config = Config.get()
    api_key = config["imgbb_api_key"]
    if not api_key:
        raise UploadError(
            "No ImgBB API key configured.\n"
            "Get one at https://api.imgbb.com/\n"
            "Then run: linuxshot config --set imgbb_api_key YOUR_KEY"
        )

    try:
        with open(filepath, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
    except OSError as e:
        raise UploadError(f"Failed to read file: {e}")

    try:
        response = requests.post(
            IMGBB_API_URL,
            data={
                "key": api_key,
                "image": image_data,
            },
            timeout=30,
        )
    except requests.ConnectionError:
        raise UploadError("No internet connection.")
    except requests.Timeout:
        raise UploadError("Upload timed out.")
    except requests.RequestException as e:
        raise UploadError(f"Upload failed: {e}")

    if response.status_code != 200:
        try:
            err = response.json().get("error", {}).get("message", f"HTTP {response.status_code}")
        except Exception:
            err = f"HTTP {response.status_code}"
        raise UploadError(f"ImgBB upload failed: {err}")

    try:
        data = response.json()["data"]
        return UploadResult(
            url=data["url"],
            delete_hash="",
            page_url=data.get("url_viewer", data["url"]),
            service="imgbb",
        )
    except (KeyError, TypeError) as e:
        raise UploadError(f"Unexpected ImgBB response: {e}")


def upload(filepath: str) -> UploadResult:
    """Upload an image using ImgBB."""
    return upload_to_imgbb(filepath)

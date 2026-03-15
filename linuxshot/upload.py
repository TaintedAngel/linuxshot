"""Image upload module for LinuxShot. Supports Imgur (anonymous + authenticated)."""

import base64
import os
import time
from dataclasses import dataclass

import requests

from .config import Config

IMGUR_API_URL = "https://api.imgur.com/3/image"


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


def upload_to_imgur(filepath: str) -> UploadResult:
    """Upload an image to Imgur anonymously.

    Args:
        filepath: Path to the image file.

    Returns:
        UploadResult with the image URL and metadata.

    Raises:
        UploadError: If the upload fails.
    """
    config = Config.get()
    client_id = config["imgur_client_id"]

    if not os.path.exists(filepath):
        raise UploadError(f"File not found: {filepath}")

    # Read and base64-encode the image
    try:
        with open(filepath, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
    except OSError as e:
        raise UploadError(f"Failed to read file: {e}")

    headers = {
        "Authorization": f"Client-ID {client_id}",
    }

    payload = {
        "image": image_data,
        "type": "base64",
        "name": os.path.basename(filepath),
    }

    last_error = ""
    response = None
    # Retry transient failures (network hiccups, 5xx responses)
    for attempt in range(1, 4):
        try:
            response = requests.post(
                IMGUR_API_URL,
                headers=headers,
                data=payload,
                timeout=30,
            )
        except requests.ConnectionError:
            last_error = "No internet connection. Upload failed."
        except requests.Timeout:
            last_error = "Upload timed out. Try again later."
        except requests.RequestException as e:
            last_error = f"Upload request failed: {e}"
        else:
            if response.status_code == 200:
                break
            if response.status_code == 429:
                last_error = (
                    "Imgur rate limit reached for the current Client ID (HTTP 429). "
                    "Set your own Imgur Client ID with: "
                    "linuxshot config --set imgur_client_id YOUR_CLIENT_ID"
                )
                break
            if response.status_code >= 500 and attempt < 3:
                # Transient server issue; retry with short backoff
                time.sleep(attempt)
                continue
            try:
                error_data = response.json()
                error_msg = error_data.get("data", {}).get("error", "Unknown error")
            except Exception:
                error_msg = f"HTTP {response.status_code}"
            last_error = f"Imgur upload failed: {error_msg}"
            break

        if attempt < 3:
            time.sleep(attempt)

    if response is None:
        raise UploadError(last_error or "Upload request failed.")

    if response.status_code != 200:
        raise UploadError(last_error or f"Imgur upload failed: HTTP {response.status_code}")

    try:
        data = response.json()["data"]
        return UploadResult(
            url=data["link"],
            delete_hash=data.get("deletehash", ""),
            page_url=f"https://imgur.com/{data.get('id', '')}",
            service="imgur",
        )
    except (KeyError, TypeError) as e:
        raise UploadError(f"Unexpected Imgur response: {e}")


def upload(filepath: str) -> UploadResult:
    """Upload an image using the configured service.

    Currently only supports Imgur. Extensible for future services.
    """
    config = Config.get()
    service = config["upload_service"]

    if service == "imgur":
        return upload_to_imgur(filepath)
    else:
        raise UploadError(f"Unknown upload service: {service}")

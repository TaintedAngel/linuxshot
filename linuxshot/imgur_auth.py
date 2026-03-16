"""Imgur OAuth2 authentication for LinuxShot.

Uses the PIN-based flow so no local HTTP server is needed:
1. Open browser → Imgur authorize page
2. User copies the PIN shown by Imgur
3. Exchange PIN for access_token + refresh_token
4. Tokens are stored in ~/.config/linuxshot/imgur_tokens.json
5. Tokens are refreshed automatically when expired
"""

import json
import os
import time
import webbrowser

import requests

from .config import Config
from .utils import get_config_dir

IMGUR_AUTHORIZE_URL = "https://api.imgur.com/oauth2/authorize"
IMGUR_TOKEN_URL = "https://api.imgur.com/oauth2/token"
TOKEN_FILE = "imgur_tokens.json"


class ImgurAuth:
    """Manages Imgur OAuth2 tokens."""

    def __init__(self):
        self._token_path = os.path.join(get_config_dir(), TOKEN_FILE)
        self._tokens: dict = {}
        self._load()

    # ── Public API ─────────────────────────────────────────────────

    @property
    def is_logged_in(self) -> bool:
        return bool(self._tokens.get("access_token"))

    @property
    def username(self) -> str:
        return self._tokens.get("account_username", "")

    @property
    def access_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if not self.is_logged_in:
            return ""
        if self._is_expired():
            self.refresh()
        return self._tokens.get("access_token", "")

    def login_interactive(self) -> bool:
        """Run the interactive PIN-based login flow (CLI).

        Opens the browser and prompts for the PIN on stdin.
        Returns True on success.
        """
        config = Config.get()
        client_id = config["imgur_client_id"]

        url = f"{IMGUR_AUTHORIZE_URL}?client_id={client_id}&response_type=pin"
        print(f"\nOpening Imgur authorization page in your browser...\n")
        print(f"If it doesn't open, visit this URL manually:\n  {url}\n")
        webbrowser.open(url)

        try:
            pin = input("Enter the PIN from Imgur: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nLogin cancelled.")
            return False

        if not pin:
            print("No PIN entered. Login cancelled.")
            return False

        return self._exchange_pin(pin)

    def refresh(self) -> bool:
        """Refresh the access token using the stored refresh_token."""
        refresh_token = self._tokens.get("refresh_token")
        if not refresh_token:
            return False

        config = Config.get()
        client_id = config["imgur_client_id"]
        client_secret = config.get("imgur_client_secret", "")

        try:
            resp = requests.post(
                IMGUR_TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                },
                timeout=15,
            )
        except requests.RequestException as e:
            print(f"Token refresh failed: {e}")
            return False

        if resp.status_code != 200:
            print(f"Token refresh failed: HTTP {resp.status_code}")
            self.logout()
            return False

        data = resp.json()
        self._tokens.update({
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at": time.time() + data.get("expires_in", 3600),
        })
        self._save()
        return True

    def logout(self) -> None:
        """Remove stored tokens."""
        self._tokens = {}
        if os.path.exists(self._token_path):
            os.remove(self._token_path)

    def get_auth_header(self) -> dict[str, str]:
        """Return the Authorization header for authenticated API calls."""
        token = self.access_token
        if token:
            return {"Authorization": f"Bearer {token}"}
        # Fall back to anonymous Client-ID auth
        config = Config.get()
        return {"Authorization": f"Client-ID {config['imgur_client_id']}"}

    # ── Internal ───────────────────────────────────────────────────

    def _exchange_pin(self, pin: str) -> bool:
        config = Config.get()
        client_id = config["imgur_client_id"]
        client_secret = config.get("imgur_client_secret", "")

        try:
            resp = requests.post(
                IMGUR_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "pin",
                    "pin": pin,
                },
                timeout=15,
            )
        except requests.RequestException as e:
            print(f"Login failed: {e}")
            return False

        if resp.status_code != 200:
            try:
                err = resp.json().get("data", {}).get("error", resp.text)
            except Exception:
                err = f"HTTP {resp.status_code}"
            print(f"Login failed: {err}")
            return False

        data = resp.json()
        self._tokens = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": time.time() + data.get("expires_in", 3600),
            "account_username": data.get("account_username", ""),
            "account_id": data.get("account_id", ""),
        }
        self._save()
        print(f"Logged in as: {self._tokens['account_username']}")
        return True

    def _is_expired(self) -> bool:
        expires_at = self._tokens.get("expires_at", 0)
        return time.time() >= (expires_at - 60)  # 60s safety margin

    def _load(self) -> None:
        if os.path.exists(self._token_path):
            try:
                with open(self._token_path, "r") as f:
                    self._tokens = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._tokens = {}
        else:
            self._tokens = {}

    def _save(self) -> None:
        try:
            with open(self._token_path, "w") as f:
                json.dump(self._tokens, f, indent=2)
            os.chmod(self._token_path, 0o600)  # tokens are sensitive
        except OSError as e:
            print(f"Warning: Failed to save tokens: {e}")

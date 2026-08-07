"""Application configuration and user settings.

All mutable data (database, logs, settings, OAuth client file) lives in
%APPDATA%/UnifiedMailbox so the installed .exe never writes next to itself.
No secrets are stored here: passwords and OAuth tokens go to the OS keyring
(see app.auth.secrets_store).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

APP_NAME = "UnifiedMailbox"

log = logging.getLogger(__name__)


def app_data_dir() -> Path:
    """Per-user writable data directory (created on first use)."""
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return app_data_dir() / "mailbox.db"


def log_dir() -> Path:
    d = app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def google_client_secrets_path() -> Path:
    """Location of the user-supplied Google OAuth client file (credentials.json)."""
    return app_data_dir() / "google_credentials.json"


_SETTINGS_FILE = "settings.json"

DEFAULTS = {
    "sync_interval_minutes": 5,
    "notifications_enabled": True,
    "messages_per_folder": 50,
}


class Settings:
    """Small JSON-backed settings store with defaults."""

    def __init__(self, path: Path | None = None):
        self.path = path or (app_data_dir() / _SETTINGS_FILE)
        self._data: dict = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                if isinstance(stored, dict):
                    self._data.update(stored)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Could not load settings (%s); using defaults", e)

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError as e:
            log.error("Could not save settings: %s", e)

    def get(self, key: str, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self.save()

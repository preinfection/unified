"""Application configuration and user settings.

All mutable data (database, logs, settings, OAuth client file) lives in
%APPDATA%/Unified so the installed .exe never writes next to itself.
No secrets are stored here: passwords and OAuth tokens go to the OS keyring
(see app.auth.secrets_store).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

APP_NAME = "Unified"

# Pre-rename name (the app used to be called "UnifiedMailbox"). Kept only so
# migration.py can find and copy over an existing install's data/secrets the
# first time this build runs - never used for new data.
LEGACY_APP_NAME = "UnifiedMailbox"

log = logging.getLogger(__name__)


def app_data_dir() -> Path:
    """Per-user writable data directory (created on first use)."""
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def legacy_app_data_dir() -> Path:
    """Where data lived under the app's old name, if this machine has one."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / LEGACY_APP_NAME


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
    # Display limit for the message list, and the increment "Load more"
    # raises it by - NOT a cap on what sync fetches/caches (sync always
    # indexes the complete mailbox in the background; this only bounds how
    # many cached rows a view materializes into the UI at once). Kept
    # small by default so the first paint of a large mailbox stays fast:
    # 100, then "Load more" -> 200, then 300, and so on.
    "messages_shown": 100,
    # Appearance. "system" follows the Windows light/dark setting; the
    # density controls how many lines each message row shows.
    "theme_mode": "system",
    "list_density": "cozy",
    # How much the interface animates: "full", "system" or "reduced".
    #
    # Defaults to "full" rather than "system", deliberately. Windows'
    # "Show animations" switch is as much a perceived-performance toggle
    # as an accessibility one - a great many machines have it off for
    # speed - and following it by default silently deletes the product's
    # entire motion design on those machines. Unified's motion is short
    # (nothing over 350ms), never loops, and never blocks input, so
    # honouring that switch by default costs far more than it protects.
    #
    # "Match Windows" is one click away in Settings > Appearance, is
    # labelled with what Windows is currently asking for, and still
    # reduces rather than removes: spatial motion goes, in-place feedback
    # stays. Anyone who needs it can have it in a second.
    "motion_mode": "full",
    # Window state. Maximised by default - a three-pane mail client in a
    # 1360px window on a large display wastes most of the screen. The
    # restored geometry is remembered separately so restore-down returns
    # to the size that was actually in use.
    "start_maximized": True,
    "window_geometry": "",
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

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


def peek_appearance() -> dict:
    """The theme and motion preference, read before anything else exists.

    WHY THIS IS SEPARATE FROM Settings. The startup window is shown the
    instant QApplication exists, which is BEFORE the background worker has
    migrated the install, decrypted the mailbox or opened the database -
    and therefore before Settings has been constructed. Without this, the
    opening surface could only ever be painted in the default dark
    palette, and a user on the light theme would watch the app open dark
    and then flip. The first frame is not the place to be wrong about
    which product this is.

    It is a small JSON read with no side effects: it never creates the
    file, never migrates anything, and falls back to the defaults on any
    error. Settings still owns the values afterwards.
    """
    out = {
        "theme_mode": DEFAULTS["theme_mode"],
        "reduced_motion": DEFAULTS["reduced_motion"],
    }
    try:
        path = app_data_dir() / _SETTINGS_FILE
        if not path.exists():
            return out
        with open(path, "r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            for key in out:
                if key in stored:
                    out[key] = stored[key]
    except (OSError, json.JSONDecodeError) as e:
        log.debug("Could not read appearance settings early (%s); using defaults", e)
    return out


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

    # ---- appearance -----------------------------------------------------
    # "dark" or "light". Both ramps are generated and contrast-measured in
    # theme.py; this is what decides which one the app binds at startup.
    # Dark is the default because PRODUCT.md's reader is at a desk in the
    # evening, which is the scene the warm palette was built from.
    "theme_mode": "dark",
    # Comfortable rows (three lines) or compact (two). A mailbox with 40
    # messages and one with 4,000 want different things, and this is the
    # one token that separates them.
    "compact_rows": False,
    # Motion off makes every transition jump to its END state rather than
    # be skipped - see app/ui/motion.py. Qt exposes no system
    # prefers-reduced-motion, so this is the app's own switch.
    "reduced_motion": False,
    # Remembered sidebar width state, so the app opens the way it was left.
    "sidebar_collapsed": False,
    # The experimental smoothed pointer (app/ui/smooth_pointer.py). Off:
    # a smoothed pointer trails the real one, which costs precision.
    "smooth_pointer": False,
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

"""One-time migration from the app's pre-rename identity ("UnifiedMailbox").

The app was renamed to "Unified", which changes two things that would
otherwise silently strand a user's existing install: the %APPDATA% folder
(config.APP_NAME) and the OS keyring service name (secrets_store.SERVICE).
Without this, upgrading would look like every account vanished and every
sign-in needed to be redone.

This runs once at startup, before Settings/Database are opened. It only
ever copies (never deletes/moves) the legacy folder, so the old data stays
in place as a backup regardless of outcome.
"""

from __future__ import annotations

import logging
import shutil

from app import config
from app.auth import secrets_store
from app.database import Database

log = logging.getLogger(__name__)

_FILES_TO_COPY = ("mailbox.db", "settings.json", "google_credentials.json")


def migrate_legacy_install() -> None:
    new_dir = config.app_data_dir()
    # A plaintext db means migration already ran (or this is a fresh install
    # of the new name); an encrypted one means it ran and the app has since
    # exited cleanly at least once. Either way, never re-migrate - re-running
    # against a since-modified new install would re-copy stale legacy data
    # over it.
    if (new_dir / "mailbox.db").exists() or (new_dir / "mailbox.db.enc").exists():
        return

    old_dir = config.legacy_app_data_dir()
    old_db = old_dir / "mailbox.db"
    if not old_db.exists():
        return  # nothing to migrate

    log.info("Migrating data from legacy install at %s", old_dir)
    try:
        for name in _FILES_TO_COPY:
            src = old_dir / name
            if src.exists():
                shutil.copy2(src, new_dir / name)
    except OSError as e:
        log.error("Legacy data copy failed: %s", e)
        return

    _migrate_secrets(new_dir / "mailbox.db")
    log.info("Legacy data migration complete")


def _migrate_secrets(db_path) -> None:
    """Re-save each account's keyring secret under the new service name."""
    try:
        db = Database(db_path)
    except Exception as e:
        log.error("Could not open migrated database to carry over sign-ins: %s", e)
        return
    try:
        for account in db.get_accounts():
            kind = (
                secrets_store.KIND_GMAIL_TOKEN
                if account["provider"] == "gmail"
                else secrets_store.KIND_IMAP_PASSWORD
            )
            secret = secrets_store.get_legacy_secret(kind, account["email"])
            if secret:
                secrets_store.set_secret(kind, account["email"], secret)
                log.info("Migrated sign-in for %s", account["email"])
            else:
                log.warning(
                    "No legacy sign-in found for %s - it will need to be "
                    "re-added", account["email"],
                )
    finally:
        db.close()

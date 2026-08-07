"""Tests for the one-time legacy-install migration (UnifiedMailbox -> Unified)."""

import json

import keyring
import pytest

from app import config, migration
from app.auth import secrets_store
from app.database import Database


@pytest.fixture()
def appdata_dirs(tmp_path, monkeypatch):
    """Isolate legacy/new app-data dirs from the real %APPDATA%."""
    root = tmp_path / "AppData"
    monkeypatch.setenv("APPDATA", str(root))
    legacy = root / config.LEGACY_APP_NAME
    new = root / config.APP_NAME
    legacy.mkdir(parents=True)
    return legacy, new


@pytest.fixture(autouse=True)
def keyring_backend():
    """A throwaway in-memory keyring backend so tests never touch the real
    Windows Credential Manager and never leave test secrets behind."""
    from keyring.backend import KeyringBackend

    class _MemoryKeyring(KeyringBackend):
        priority = 1

        def __init__(self):
            self._store: dict[tuple[str, str], str] = {}

        def set_password(self, service, username, password):
            self._store[(service, username)] = password

        def get_password(self, service, username):
            return self._store.get((service, username))

        def delete_password(self, service, username):
            self._store.pop((service, username), None)

    previous = keyring.get_keyring()
    keyring.set_keyring(_MemoryKeyring())
    yield
    keyring.set_keyring(previous)


def test_no_legacy_dir_is_a_noop(appdata_dirs, tmp_path):
    legacy, new = appdata_dirs
    (legacy / "mailbox.db").unlink(missing_ok=True)  # no legacy db present
    migration.migrate_legacy_install()
    assert not (new / "mailbox.db").exists()


def test_migrates_database_settings_and_secrets(appdata_dirs):
    legacy, new = appdata_dirs

    # Build a legacy database with one Gmail and one IMAP account.
    legacy_db = Database(legacy / "mailbox.db")
    gmail_id = legacy_db.add_account("user@gmail.com", "gmail")
    imap_id = legacy_db.add_account(
        "user@example.com", "imap", imap_host="imap.example.com", imap_port=993,
        smtp_host="smtp.example.com", smtp_port=587,
    )
    legacy_db.upsert_email({
        "account_id": gmail_id, "uid": "1", "folder": "inbox",
        "subject": "Hello", "date_ts": 100,
    })
    legacy_db.close()

    (legacy / "settings.json").write_text(json.dumps({"sync_interval_minutes": 7}))
    (legacy / "google_credentials.json").write_text(json.dumps({"installed": {}}))

    # Secrets stored under the legacy keyring service name.
    keyring.set_password(
        config.LEGACY_APP_NAME, "gmail-token:user@gmail.com", "legacy-oauth-token"
    )
    keyring.set_password(
        config.LEGACY_APP_NAME, "imap-password:user@example.com", "legacy-password"
    )

    migration.migrate_legacy_install()

    # Database + settings + Google client file all copied.
    assert (new / "mailbox.db").exists()
    assert json.loads((new / "settings.json").read_text())["sync_interval_minutes"] == 7
    assert (new / "google_credentials.json").exists()

    migrated_db = Database(new / "mailbox.db")
    accounts = {a["email"]: a for a in migrated_db.get_accounts()}
    assert set(accounts) == {"user@gmail.com", "user@example.com"}
    assert migrated_db.list_emails("inbox")[0]["subject"] == "Hello"
    migrated_db.close()

    # Secrets re-saved under the new service name.
    assert secrets_store.get_secret(
        secrets_store.KIND_GMAIL_TOKEN, "user@gmail.com"
    ) == "legacy-oauth-token"
    assert secrets_store.get_secret(
        secrets_store.KIND_IMAP_PASSWORD, "user@example.com"
    ) == "legacy-password"

    # Legacy folder is left untouched (copy, not move).
    assert (legacy / "mailbox.db").exists()


def test_missing_secret_is_logged_not_fatal(appdata_dirs, caplog):
    legacy, new = appdata_dirs
    legacy_db = Database(legacy / "mailbox.db")
    legacy_db.add_account("nosaved@gmail.com", "gmail")
    legacy_db.close()

    # No keyring entry was ever set for this account.
    migration.migrate_legacy_install()

    assert (new / "mailbox.db").exists()
    assert secrets_store.get_secret(
        secrets_store.KIND_GMAIL_TOKEN, "nosaved@gmail.com"
    ) is None


def test_already_migrated_is_a_noop(appdata_dirs):
    legacy, new = appdata_dirs
    legacy_db = Database(legacy / "mailbox.db")
    legacy_db.add_account("a@gmail.com", "gmail")
    legacy_db.close()

    migration.migrate_legacy_install()
    new_db_mtime = (new / "mailbox.db").stat().st_mtime

    # A second run must not re-copy (the new db already has data).
    migration.migrate_legacy_install()
    assert (new / "mailbox.db").stat().st_mtime == new_db_mtime

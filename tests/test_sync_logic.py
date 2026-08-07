"""Tests for sync bookkeeping: migration, timestamps, notification gating."""

import sqlite3
import time

import pytest

from app.database import Database
from app.services.sync_service import should_notify


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


# ---------------------------------------------------------------- migration


def test_migration_adds_sync_columns(tmp_path):
    """A database created by the first release gets the new columns added."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT,
            provider TEXT NOT NULL,
            imap_host TEXT, imap_port INTEGER,
            smtp_host TEXT, smtp_port INTEGER,
            created_at INTEGER NOT NULL)"""
    )
    conn.execute(
        "INSERT INTO accounts (email, provider, created_at)"
        " VALUES ('a@example.com', 'gmail', 1)"
    )
    conn.commit()
    conn.close()

    db = Database(path)
    account = db.get_account_by_email("a@example.com")
    assert account["initial_sync_completed"] == 0
    assert account["last_notification_check"] == 0
    db.close()


def test_sync_timestamps(db):
    account_id = db.add_account("a@example.com", "gmail")
    assert db.get_account(account_id)["initial_sync_completed"] == 0

    db.mark_initial_sync_completed(account_id, 1234)
    db.set_last_notification_check(account_id, 5678)
    account = db.get_account(account_id)
    assert account["initial_sync_completed"] == 1234
    assert account["last_notification_check"] == 5678

    # Defaults to "now" when no timestamp given
    db.mark_initial_sync_completed(account_id)
    assert db.get_account(account_id)["initial_sync_completed"] >= int(time.time()) - 5


# ---------------------------------------------------------- notification gate


def _msg(**overrides):
    msg = {"folder": "inbox", "is_read": 0, "date_ts": int(time.time())}
    msg.update(overrides)
    return msg


def test_initial_import_never_notifies():
    account = {"initial_sync_completed": 0, "last_notification_check": 0}
    assert should_notify(account, _msg(), is_new=True) is False


def test_new_unread_after_initial_sync_notifies():
    now = int(time.time())
    account = {
        "initial_sync_completed": now - 3600,
        "last_notification_check": now - 300,
    }
    assert should_notify(account, _msg(), is_new=True) is True


def test_existing_message_update_does_not_notify():
    account = {"initial_sync_completed": 100, "last_notification_check": 100}
    assert should_notify(account, _msg(), is_new=False) is False


def test_read_or_non_inbox_does_not_notify():
    now = int(time.time())
    account = {"initial_sync_completed": now, "last_notification_check": 0}
    assert should_notify(account, _msg(is_read=1), is_new=True) is False
    assert should_notify(account, _msg(folder="sent"), is_new=True) is False


def test_old_dated_reappearing_mail_does_not_notify():
    now = int(time.time())
    account = {
        "initial_sync_completed": now - 10 * 86400,
        "last_notification_check": now - 60,
    }
    old = _msg(date_ts=now - 5 * 86400)  # dated well before the last check
    assert should_notify(account, old, is_new=True) is False

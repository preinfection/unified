"""Tests for metadata-first sync storage: lazy bodies, batching, counting."""

import pytest

from app.database import Database
from app.email.message_parser import parse_headers


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def meta_msg(account_id, uid, **overrides):
    msg = {
        "account_id": account_id,
        "uid": uid,
        "folder": "inbox",
        "sender_name": "A",
        "sender_email": "a@x.com",
        "recipients": "me",
        "subject": f"Subject {uid}",
        "snippet": "snip",
        "body_text": "",
        "body_html": "",
        "date_ts": 100,
        "is_read": 0,
        "is_starred": 0,
        "has_attachments": 0,
        "body_fetched": 0,
    }
    msg.update(overrides)
    return msg


def test_metadata_update_never_wipes_fetched_body(db):
    """The blank-preview bug: a later metadata sync must keep stored bodies."""
    aid = db.add_account("a@example.com", "gmail")
    db.upsert_email(meta_msg(aid, "u1"))
    db.update_body(1, "the text body", "<p>the html body</p>", True)

    row = db.get_email(1)
    assert row["body_fetched"] == 1
    assert row["has_attachments"] == 1

    # Sync runs again and upserts metadata (flags changed, no body)
    db.upsert_email(meta_msg(aid, "u1", is_read=1))
    row = db.get_email(1)
    assert row["is_read"] == 1                      # flag updated
    assert row["body_text"] == "the text body"      # body preserved
    assert row["body_html"] == "<p>the html body</p>"
    assert row["body_fetched"] == 1
    assert row["has_attachments"] == 1


def test_full_upsert_still_stores_body(db):
    aid = db.add_account("a@example.com", "gmail")
    db.upsert_email(meta_msg(aid, "u1", body_text="full", body_fetched=1))
    row = db.get_email(1)
    assert row["body_text"] == "full"
    assert row["body_fetched"] == 1


def test_batch_upsert(db):
    aid = db.add_account("a@example.com", "gmail")
    db.upsert_emails([meta_msg(aid, f"u{i}") for i in range(250)])
    assert db.count_emails("inbox", account_id=aid) == 250
    # Batch upsert of the same uids does not duplicate
    db.upsert_emails([meta_msg(aid, f"u{i}") for i in range(250)])
    assert db.count_emails("inbox", account_id=aid) == 250


def test_get_folder_uids(db):
    aid = db.add_account("a@example.com", "gmail")
    db.upsert_emails([meta_msg(aid, "x"), meta_msg(aid, "y", folder="sent")])
    assert set(db.get_folder_uids(aid, "inbox")) == {"x"}
    assert set(db.get_folder_uids(aid, "sent")) == {"y"}


def test_count_matches_list_filters(db):
    aid = db.add_account("a@example.com", "gmail")
    db.upsert_emails(
        [meta_msg(aid, f"u{i}", subject=f"Report {i}") for i in range(30)]
    )
    assert db.count_emails("inbox") == 30
    assert db.count_emails("inbox", search="Report 7") == 1
    listed = db.list_emails("inbox", limit=10)
    assert len(listed) == 10  # display limit
    assert db.count_emails("inbox") == 30  # count unaffected by limit


def test_body_fetched_migration(tmp_path):
    """Old databases: rows with bodies are marked fetched, empty ones not."""
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE, display_name TEXT,
            provider TEXT NOT NULL, imap_host TEXT, imap_port INTEGER,
            smtp_host TEXT, smtp_port INTEGER, created_at INTEGER NOT NULL,
            initial_sync_completed INTEGER NOT NULL DEFAULT 0,
            last_notification_check INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            uid TEXT NOT NULL, folder TEXT NOT NULL,
            sender_name TEXT DEFAULT '', sender_email TEXT DEFAULT '',
            recipients TEXT DEFAULT '', subject TEXT DEFAULT '',
            snippet TEXT DEFAULT '', body_text TEXT DEFAULT '',
            body_html TEXT DEFAULT '', date_ts INTEGER DEFAULT 0,
            is_read INTEGER NOT NULL DEFAULT 0,
            is_starred INTEGER NOT NULL DEFAULT 0,
            has_attachments INTEGER NOT NULL DEFAULT 0,
            UNIQUE (account_id, folder, uid));
        INSERT INTO accounts (email, provider, created_at)
            VALUES ('a@x.com', 'gmail', 1);
        INSERT INTO emails (account_id, uid, folder, body_text)
            VALUES (1, 'with-body', 'inbox', 'hello');
        INSERT INTO emails (account_id, uid, folder)
            VALUES (1, 'no-body', 'inbox');
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    rows = {e["uid"]: e for e in db.list_emails("inbox")}
    assert rows["with-body"]["body_fetched"] == 1
    assert rows["no-body"]["body_fetched"] == 0
    db.close()


def test_parse_headers_shape():
    raw = (
        b"From: Alice <alice@example.com>\r\n"
        b"To: me@example.com\r\n"
        b"Subject: Header only\r\n"
        b"Date: Thu, 06 Aug 2026 12:30:00 +0000\r\n\r\n"
    )
    parsed = parse_headers(raw, account_id=1, folder="inbox", uid="9",
                           is_read=True)
    assert parsed["subject"] == "Header only"
    assert parsed["sender_email"] == "alice@example.com"
    assert parsed["body_fetched"] == 0
    assert parsed["body_text"] == ""
    assert parsed["is_read"] == 1
    assert parsed["date_ts"] > 0

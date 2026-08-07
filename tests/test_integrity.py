"""Tests for the startup database integrity check and repair."""

import sqlite3

import pytest

from app.database import Database


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def test_clean_database_passes(db):
    db.add_account("a@example.com", "gmail")
    report = db.check_and_repair()
    assert report["ok"] is True
    assert report["problems"] == []
    assert report["repaired"] == []


def test_orphaned_emails_are_repaired(tmp_path):
    path = tmp_path / "orphan.db"
    db = Database(path)
    aid = db.add_account("a@example.com", "gmail")
    db.upsert_email({"account_id": aid, "uid": "keep", "folder": "inbox"})
    db.close()

    # Simulate a crash artifact: a message row pointing at a missing account.
    # (Raw connection without the foreign_keys pragma enforces nothing.)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO emails (account_id, uid, folder) VALUES (999, 'orphan', 'inbox')"
    )
    conn.commit()
    conn.close()

    db = Database(path)
    report = db.check_and_repair()
    assert report["ok"] is True
    assert any("removed accounts" in p for p in report["problems"])
    assert any("orphaned" in r for r in report["repaired"])
    uids = db.get_folder_uids(aid, "inbox")
    assert uids == ["keep"]
    # A second check is clean.
    assert db.check_and_repair()["problems"] == []
    db.close()


def test_invalid_folder_rows_are_repaired(tmp_path):
    path = tmp_path / "badfolder.db"
    db = Database(path)
    aid = db.add_account("a@example.com", "gmail")
    db.close()

    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO emails (account_id, uid, folder)"
        " VALUES (?, 'weird', 'NotAFolder')",
        (aid,),
    )
    conn.commit()
    conn.close()

    db = Database(path)
    report = db.check_and_repair()
    assert any("invalid folder" in p for p in report["problems"])
    assert db.count_emails("inbox", account_id=aid) == 0
    db.close()

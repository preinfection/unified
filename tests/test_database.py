"""Tests for the SQLite storage layer."""

import pytest

from app.database import Database


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def make_msg(account_id, uid="m1", folder="inbox", **overrides):
    msg = {
        "account_id": account_id,
        "uid": uid,
        "folder": folder,
        "sender_name": "Alice Example",
        "sender_email": "alice@example.com",
        "recipients": "me@example.com",
        "subject": "Hello",
        "snippet": "Hello there",
        "body_text": "Hello there, full body.",
        "body_html": "",
        "date_ts": 1_700_000_000,
        "is_read": 0,
        "is_starred": 0,
        "has_attachments": 0,
    }
    msg.update(overrides)
    return msg


def test_add_and_get_accounts(db):
    account_id = db.add_account("User@Example.com", "imap",
                                imap_host="imap.example.com", imap_port=993,
                                smtp_host="smtp.example.com", smtp_port=587)
    accounts = db.get_accounts()
    assert len(accounts) == 1
    # Email is normalized to lowercase
    assert accounts[0]["email"] == "user@example.com"
    assert db.get_account(account_id)["provider"] == "imap"
    assert db.get_account_by_email("USER@example.com") is not None


def test_duplicate_account_rejected(db):
    db.add_account("a@example.com", "gmail")
    with pytest.raises(Exception):
        db.add_account("a@example.com", "gmail")


def test_upsert_dedupes_and_reports_new(db):
    account_id = db.add_account("a@example.com", "gmail")
    assert db.upsert_email(make_msg(account_id)) is True
    # Same (account, folder, uid) again: update, not a new message
    assert db.upsert_email(make_msg(account_id, is_read=1)) is False
    emails = db.list_emails("inbox")
    assert len(emails) == 1
    assert emails[0]["is_read"] == 1  # remote flag update applied


def test_unified_inbox_across_accounts(db):
    a1 = db.add_account("a@example.com", "gmail")
    a2 = db.add_account("b@example.com", "imap")
    db.upsert_email(make_msg(a1, uid="x", date_ts=200))
    db.upsert_email(make_msg(a2, uid="y", date_ts=100))
    unified = db.list_emails("inbox")
    assert [e["account_email"] for e in unified] == ["a@example.com", "b@example.com"]
    only_a2 = db.list_emails("inbox", account_id=a2)
    assert len(only_a2) == 1


def test_search(db):
    account_id = db.add_account("a@example.com", "gmail")
    db.upsert_email(make_msg(account_id, uid="1", subject="Quarterly report"))
    db.upsert_email(make_msg(account_id, uid="2", subject="Lunch?"))
    hits = db.list_emails("inbox", search="quarterly")
    assert len(hits) == 1
    assert hits[0]["subject"] == "Quarterly report"


def test_unread_counts_and_mark_read(db):
    account_id = db.add_account("a@example.com", "gmail")
    db.upsert_email(make_msg(account_id, uid="1"))
    db.upsert_email(make_msg(account_id, uid="2", is_read=1))
    counts = db.unread_counts()
    assert counts["total"] == 1
    assert counts["per_account"][account_id] == 1
    unread = [e for e in db.list_emails("inbox") if not e["is_read"]][0]
    db.set_read(unread["id"], True)
    assert db.unread_counts()["total"] == 0
    db.set_read(unread["id"], False)
    assert db.unread_counts()["total"] == 1


def test_star_and_starred_view(db):
    account_id = db.add_account("a@example.com", "gmail")
    db.upsert_email(make_msg(account_id, uid="1"))
    email_id = db.list_emails("inbox")[0]["id"]
    db.set_starred(email_id, True)
    starred = db.list_emails(starred_only=True)
    assert len(starred) == 1
    db.set_starred(email_id, False)
    assert db.list_emails(starred_only=True) == []


def test_move_to_trash(db):
    account_id = db.add_account("a@example.com", "gmail")
    db.upsert_email(make_msg(account_id, uid="1"))
    email_id = db.list_emails("inbox")[0]["id"]
    db.move_to_trash(email_id)
    assert db.list_emails("inbox") == []
    assert len(db.list_emails("trash")) == 1


def test_replace_folder_uids_prunes_deleted(db):
    account_id = db.add_account("a@example.com", "gmail")
    db.upsert_email(make_msg(account_id, uid="1"))
    db.upsert_email(make_msg(account_id, uid="2"))
    db.replace_folder_uids(account_id, "inbox", ["2"])
    remaining = db.list_emails("inbox")
    assert [e["uid"] for e in remaining] == ["2"]


def test_remove_account_cascades(db):
    account_id = db.add_account("a@example.com", "gmail")
    db.upsert_email(make_msg(account_id, uid="1"))
    db.remove_account(account_id)
    assert db.get_accounts() == []
    assert db.list_emails("inbox") == []

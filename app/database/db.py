"""SQLite storage for accounts and cached emails.

The Database object is shared across threads; sqlite3 connections are not,
so each thread gets its own connection via threading.local. All writes are
short transactions, and WAL mode keeps readers and writers from blocking
each other.

Folders are normalized to: 'inbox', 'sent', 'trash'. Starred is a flag,
not a folder. Emails are deduplicated per (account_id, folder, uid).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

log = logging.getLogger(__name__)

FOLDERS = ("inbox", "sent", "trash")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    display_name  TEXT,
    provider      TEXT NOT NULL CHECK (provider IN ('gmail', 'imap')),
    imap_host     TEXT,
    imap_port     INTEGER,
    smtp_host     TEXT,
    smtp_port     INTEGER,
    created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS emails (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    uid             TEXT NOT NULL,
    folder          TEXT NOT NULL,
    sender_name     TEXT DEFAULT '',
    sender_email    TEXT DEFAULT '',
    recipients      TEXT DEFAULT '',
    subject         TEXT DEFAULT '',
    snippet         TEXT DEFAULT '',
    body_text       TEXT DEFAULT '',
    body_html       TEXT DEFAULT '',
    date_ts         INTEGER DEFAULT 0,
    is_read         INTEGER NOT NULL DEFAULT 0,
    is_starred      INTEGER NOT NULL DEFAULT 0,
    has_attachments INTEGER NOT NULL DEFAULT 0,
    UNIQUE (account_id, folder, uid)
);

CREATE INDEX IF NOT EXISTS idx_emails_folder_date ON emails (folder, date_ts DESC);
CREATE INDEX IF NOT EXISTS idx_emails_account ON emails (account_id);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._local = threading.local()
        self._init_lock = threading.Lock()
        # Create schema once, from the constructing thread.
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn: Optional[sqlite3.Connection] = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn: Optional[sqlite3.Connection] = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ------------------------------------------------------------------ accounts

    def add_account(
        self,
        email: str,
        provider: str,
        display_name: str = "",
        imap_host: str = "",
        imap_port: int = 0,
        smtp_host: str = "",
        smtp_port: int = 0,
    ) -> int:
        conn = self._connect()
        with conn:
            cur = conn.execute(
                "INSERT INTO accounts (email, display_name, provider, imap_host,"
                " imap_port, smtp_host, smtp_port, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    email.strip().lower(),
                    display_name,
                    provider,
                    imap_host,
                    imap_port,
                    smtp_host,
                    smtp_port,
                    int(time.time()),
                ),
            )
        return int(cur.lastrowid)

    def remove_account(self, account_id: int) -> None:
        conn = self._connect()
        with conn:
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    def get_accounts(self) -> list[dict]:
        rows = self._connect().execute(
            "SELECT * FROM accounts ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_account(self, account_id: int) -> Optional[dict]:
        row = self._connect().execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_account_by_email(self, email: str) -> Optional[dict]:
        row = self._connect().execute(
            "SELECT * FROM accounts WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return dict(row) if row else None

    # -------------------------------------------------------------------- emails

    def upsert_email(self, msg: dict) -> bool:
        """Insert or update a cached message.

        Returns True when the message was newly inserted (used to count new
        mail for notifications). Remote flags (read/starred) win on update
        because the server is the source of truth for them.
        """
        conn = self._connect()
        is_new = not self.email_exists(msg["account_id"], msg["folder"], msg["uid"])
        with conn:
            conn.execute(
                """
                INSERT INTO emails (account_id, uid, folder, sender_name, sender_email,
                    recipients, subject, snippet, body_text, body_html, date_ts,
                    is_read, is_starred, has_attachments)
                VALUES (:account_id, :uid, :folder, :sender_name, :sender_email,
                    :recipients, :subject, :snippet, :body_text, :body_html, :date_ts,
                    :is_read, :is_starred, :has_attachments)
                ON CONFLICT (account_id, folder, uid) DO UPDATE SET
                    is_read = excluded.is_read,
                    is_starred = excluded.is_starred,
                    has_attachments = excluded.has_attachments,
                    snippet = excluded.snippet,
                    body_text = excluded.body_text,
                    body_html = excluded.body_html
                """,
                {
                    "sender_name": "",
                    "sender_email": "",
                    "recipients": "",
                    "subject": "",
                    "snippet": "",
                    "body_text": "",
                    "body_html": "",
                    "date_ts": 0,
                    "is_read": 0,
                    "is_starred": 0,
                    "has_attachments": 0,
                    **msg,
                },
            )
        return is_new

    def email_exists(self, account_id: int, folder: str, uid: str) -> bool:
        row = self._connect().execute(
            "SELECT 1 FROM emails WHERE account_id=? AND folder=? AND uid=?",
            (account_id, folder, uid),
        ).fetchone()
        return row is not None

    def list_emails(
        self,
        folder: str = "inbox",
        account_id: Optional[int] = None,
        starred_only: bool = False,
        search: str = "",
        limit: int = 500,
    ) -> list[dict]:
        """Query the unified message list, newest first."""
        clauses: list[str] = []
        params: list[Any] = []
        if starred_only:
            clauses.append("e.is_starred = 1 AND e.folder != 'trash'")
        else:
            clauses.append("e.folder = ?")
            params.append(folder)
        if account_id is not None:
            clauses.append("e.account_id = ?")
            params.append(account_id)
        if search:
            like = f"%{search}%"
            clauses.append(
                "(e.subject LIKE ? OR e.sender_name LIKE ? OR e.sender_email LIKE ?"
                " OR e.snippet LIKE ? OR e.body_text LIKE ?)"
            )
            params += [like, like, like, like, like]
        sql = (
            "SELECT e.*, a.email AS account_email FROM emails e"
            " JOIN accounts a ON a.id = e.account_id"
            f" WHERE {' AND '.join(clauses)}"
            " ORDER BY e.date_ts DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._connect().execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_email(self, email_id: int) -> Optional[dict]:
        row = self._connect().execute(
            "SELECT e.*, a.email AS account_email, a.provider FROM emails e"
            " JOIN accounts a ON a.id = e.account_id WHERE e.id = ?",
            (email_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_read(self, email_id: int, is_read: bool = True) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE emails SET is_read = ? WHERE id = ?",
                (1 if is_read else 0, email_id),
            )

    def set_starred(self, email_id: int, starred: bool) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE emails SET is_starred = ? WHERE id = ?",
                (1 if starred else 0, email_id),
            )

    def move_to_trash(self, email_id: int) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE OR REPLACE emails SET folder = 'trash' WHERE id = ?",
                (email_id,),
            )

    def unread_counts(self) -> dict:
        """Return {'total': n, 'per_account': {account_id: n}} for the inbox."""
        rows = self._connect().execute(
            "SELECT account_id, COUNT(*) AS n FROM emails"
            " WHERE folder = 'inbox' AND is_read = 0 GROUP BY account_id"
        ).fetchall()
        per_account = {r["account_id"]: r["n"] for r in rows}
        return {"total": sum(per_account.values()), "per_account": per_account}

    def replace_folder_uids(
        self, account_id: int, folder: str, keep_uids: Iterable[str]
    ) -> None:
        """Delete cached messages that no longer exist server-side in a folder."""
        keep = list(keep_uids)
        conn = self._connect()
        with conn:
            if keep:
                placeholders = ",".join("?" for _ in keep)
                conn.execute(
                    f"DELETE FROM emails WHERE account_id=? AND folder=?"
                    f" AND uid NOT IN ({placeholders})",
                    [account_id, folder, *keep],
                )
            else:
                conn.execute(
                    "DELETE FROM emails WHERE account_id=? AND folder=?",
                    (account_id, folder),
                )

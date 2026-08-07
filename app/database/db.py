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
    created_at    INTEGER NOT NULL,
    initial_sync_completed  INTEGER NOT NULL DEFAULT 0,
    last_notification_check INTEGER NOT NULL DEFAULT 0
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
    body_fetched    INTEGER NOT NULL DEFAULT 0,
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
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns introduced after the first release to existing databases."""
        cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
        for name in ("initial_sync_completed", "last_notification_check"):
            if name not in cols:
                conn.execute(
                    f"ALTER TABLE accounts ADD COLUMN {name}"
                    " INTEGER NOT NULL DEFAULT 0"
                )
        email_cols = {row[1] for row in conn.execute("PRAGMA table_info(emails)")}
        if "body_fetched" not in email_cols:
            conn.execute(
                "ALTER TABLE emails ADD COLUMN body_fetched"
                " INTEGER NOT NULL DEFAULT 0"
            )
            # Rows cached by earlier versions already carry their bodies.
            conn.execute(
                "UPDATE emails SET body_fetched = 1"
                " WHERE body_text != '' OR body_html != ''"
            )

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

    def mark_initial_sync_completed(self, account_id: int, ts: int | None = None) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE accounts SET initial_sync_completed = ? WHERE id = ?",
                (ts or int(time.time()), account_id),
            )

    def set_last_notification_check(self, account_id: int, ts: int | None = None) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE accounts SET last_notification_check = ? WHERE id = ?",
                (ts or int(time.time()), account_id),
            )

    # -------------------------------------------------------------------- emails

    # A metadata-only update (body_fetched=0) must never erase a body that a
    # previous full fetch already stored - hence the CASE guards.
    _UPSERT_SQL = """
        INSERT INTO emails (account_id, uid, folder, sender_name, sender_email,
            recipients, subject, snippet, body_text, body_html, date_ts,
            is_read, is_starred, has_attachments, body_fetched)
        VALUES (:account_id, :uid, :folder, :sender_name, :sender_email,
            :recipients, :subject, :snippet, :body_text, :body_html, :date_ts,
            :is_read, :is_starred, :has_attachments, :body_fetched)
        ON CONFLICT (account_id, folder, uid) DO UPDATE SET
            is_read = excluded.is_read,
            is_starred = excluded.is_starred,
            snippet = excluded.snippet,
            has_attachments = CASE WHEN excluded.body_fetched = 1
                THEN excluded.has_attachments ELSE has_attachments END,
            body_text = CASE WHEN excluded.body_fetched = 1
                THEN excluded.body_text ELSE body_text END,
            body_html = CASE WHEN excluded.body_fetched = 1
                THEN excluded.body_html ELSE body_html END,
            body_fetched = MAX(body_fetched, excluded.body_fetched)
    """

    _MSG_DEFAULTS = {
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
        "body_fetched": 0,
    }

    def upsert_email(self, msg: dict) -> bool:
        """Insert or update a cached message.

        Returns True when the message was newly inserted (used to count new
        mail for notifications). Remote flags (read/starred) win on update
        because the server is the source of truth for them.
        """
        conn = self._connect()
        is_new = not self.email_exists(msg["account_id"], msg["folder"], msg["uid"])
        with conn:
            conn.execute(self._UPSERT_SQL, {**self._MSG_DEFAULTS, **msg})
        return is_new

    def upsert_emails(self, msgs: list[dict]) -> None:
        """Batch upsert in a single transaction - one commit per hundreds of
        messages instead of one per message, which is what makes large
        initial imports fast."""
        if not msgs:
            return
        conn = self._connect()
        with conn:
            conn.executemany(
                self._UPSERT_SQL, [{**self._MSG_DEFAULTS, **m} for m in msgs]
            )

    def update_body(
        self, email_id: int, body_text: str, body_html: str, has_attachments: bool
    ) -> None:
        """Store a lazily fetched body and mark it available."""
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE emails SET body_text = ?, body_html = ?,"
                " has_attachments = ?, body_fetched = 1 WHERE id = ?",
                (body_text, body_html, 1 if has_attachments else 0, email_id),
            )

    def get_missing_body_uids(
        self, account_id: int, folder: str, limit: int = 200
    ) -> list[str]:
        """Newest messages whose bodies have not been downloaded yet."""
        rows = self._connect().execute(
            "SELECT uid FROM emails WHERE account_id = ? AND folder = ?"
            " AND body_fetched = 0 ORDER BY date_ts DESC LIMIT ?",
            (account_id, folder, limit),
        ).fetchall()
        return [r["uid"] for r in rows]

    def check_and_repair(self) -> dict:
        """Startup integrity check. Returns {'ok', 'problems', 'repaired'}.

        Never raises for data problems - it repairs what it can and reports
        the rest so the UI can tell the user instead of crashing.
        """
        report = {"ok": True, "problems": [], "repaired": []}
        conn = self._connect()
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
            if row is None or row[0] != "ok":
                report["ok"] = False
                report["problems"].append(
                    f"database integrity: {row[0] if row else 'unknown'}"
                )
                return report  # structural damage; do not attempt row surgery
        except sqlite3.DatabaseError as e:
            report["ok"] = False
            report["problems"].append(f"database unreadable: {e}")
            return report

        # Duplicate message ids (the unique index should prevent these; a
        # crash mid-migration could leave them behind).
        dup = conn.execute(
            "SELECT COUNT(*) AS n FROM (SELECT 1 FROM emails"
            " GROUP BY account_id, folder, uid HAVING COUNT(*) > 1)"
        ).fetchone()["n"]
        if dup:
            report["problems"].append(f"{dup} duplicate message ids")
            with conn:
                conn.execute(
                    "DELETE FROM emails WHERE id NOT IN"
                    " (SELECT MIN(id) FROM emails"
                    "  GROUP BY account_id, folder, uid)"
                )
            report["repaired"].append(f"removed {dup} duplicate message groups")

        # Orphaned messages whose account no longer exists.
        orphans = conn.execute(
            "SELECT COUNT(*) AS n FROM emails WHERE account_id NOT IN"
            " (SELECT id FROM accounts)"
        ).fetchone()["n"]
        if orphans:
            report["problems"].append(f"{orphans} messages from removed accounts")
            with conn:
                conn.execute(
                    "DELETE FROM emails WHERE account_id NOT IN"
                    " (SELECT id FROM accounts)"
                )
            report["repaired"].append(f"removed {orphans} orphaned messages")

        # Rows violating folder vocabulary (corrupt writes).
        bad = conn.execute(
            "SELECT COUNT(*) AS n FROM emails WHERE folder NOT IN"
            " ('inbox', 'sent', 'trash')"
        ).fetchone()["n"]
        if bad:
            report["problems"].append(f"{bad} rows with invalid folder")
            with conn:
                conn.execute(
                    "DELETE FROM emails WHERE folder NOT IN"
                    " ('inbox', 'sent', 'trash')"
                )
            report["repaired"].append(f"removed {bad} invalid rows")

        return report

    def get_folder_uids(self, account_id: int, folder: str) -> list[str]:
        rows = self._connect().execute(
            "SELECT uid FROM emails WHERE account_id = ? AND folder = ?",
            (account_id, folder),
        ).fetchall()
        return [r["uid"] for r in rows]

    def count_emails(
        self,
        folder: str = "inbox",
        account_id: Optional[int] = None,
        starred_only: bool = False,
        search: str = "",
    ) -> int:
        """Count with the same filters as list_emails (for 'showing X of Y')."""
        clauses: list[str] = []
        params: list[Any] = []
        if starred_only:
            clauses.append("is_starred = 1 AND folder != 'trash'")
        else:
            clauses.append("folder = ?")
            params.append(folder)
        if account_id is not None:
            clauses.append("account_id = ?")
            params.append(account_id)
        if search:
            like = f"%{search}%"
            clauses.append(
                "(subject LIKE ? OR sender_name LIKE ? OR sender_email LIKE ?"
                " OR snippet LIKE ? OR body_text LIKE ?)"
            )
            params += [like, like, like, like, like]
        row = self._connect().execute(
            f"SELECT COUNT(*) AS n FROM emails WHERE {' AND '.join(clauses)}",
            params,
        ).fetchone()
        return int(row["n"])

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
                # A temp table sidesteps SQLite's bound-parameter limit for
                # mailboxes with tens of thousands of messages.
                conn.execute(
                    "CREATE TEMP TABLE IF NOT EXISTS keep_uids (uid TEXT PRIMARY KEY)"
                )
                conn.execute("DELETE FROM keep_uids")
                conn.executemany(
                    "INSERT OR IGNORE INTO keep_uids VALUES (?)",
                    [(u,) for u in keep],
                )
                conn.execute(
                    "DELETE FROM emails WHERE account_id=? AND folder=?"
                    " AND uid NOT IN (SELECT uid FROM keep_uids)",
                    (account_id, folder),
                )
                conn.execute("DELETE FROM keep_uids")
            else:
                conn.execute(
                    "DELETE FROM emails WHERE account_id=? AND folder=?",
                    (account_id, folder),
                )

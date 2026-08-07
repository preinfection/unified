"""IMAP client for custom accounts (SSL, password from the OS keyring)."""

from __future__ import annotations

import imaplib
import logging
from typing import Optional

from app.auth import secrets_store
from app.email.message_parser import parse_rfc822

log = logging.getLogger(__name__)

# Common server-side names tried, in order, for each app folder.
FOLDER_CANDIDATES = {
    "inbox": ["INBOX"],
    "sent": ["Sent", "INBOX.Sent", "Sent Items", "Sent Messages", "[Gmail]/Sent Mail"],
    "trash": ["Trash", "INBOX.Trash", "Deleted Items", "Deleted", "[Gmail]/Trash"],
}


class ImapClientError(Exception):
    pass


class ImapClient:
    def __init__(self, account: dict):
        """account is a row dict from the accounts table (provider='imap')."""
        self.account = account
        self.email = account["email"]
        password = secrets_store.get_secret(
            secrets_store.KIND_IMAP_PASSWORD, self.email
        )
        if not password:
            raise ImapClientError(
                f"No stored password for {self.email}; re-add the account."
            )
        try:
            self.conn = imaplib.IMAP4_SSL(
                account["imap_host"], int(account["imap_port"] or 993)
            )
            self.conn.login(self.email, password)
        except (imaplib.IMAP4.error, OSError) as e:
            raise ImapClientError(f"IMAP connection failed for {self.email}: {e}") from e
        self._selected: Optional[str] = None

    def close(self) -> None:
        try:
            self.conn.logout()
        except (imaplib.IMAP4.error, OSError):
            pass

    # ------------------------------------------------------------------- folders

    def _select_folder(self, folder: str, readonly: bool = True) -> Optional[str]:
        """Select the first server mailbox matching an app folder; None if absent."""
        for name in FOLDER_CANDIDATES.get(folder, [folder]):
            try:
                status, _ = self.conn.select(f'"{name}"', readonly=readonly)
            except imaplib.IMAP4.error:
                continue
            if status == "OK":
                self._selected = name
                return name
        return None

    # ------------------------------------------------------------------ fetching

    def fetch_folder(
        self, folder: str, account_id: int, max_messages: int = 50
    ) -> list[dict]:
        """Fetch the newest messages of a folder as message dicts."""
        if self._select_folder(folder, readonly=True) is None:
            log.info("Account %s has no '%s' folder", self.email, folder)
            return []
        status, data = self.conn.uid("SEARCH", None, "ALL")
        if status != "OK":
            raise ImapClientError(f"IMAP search failed in {folder}")
        uids = data[0].split()
        messages: list[dict] = []
        for uid_bytes in reversed(uids[-max_messages:]):
            uid = uid_bytes.decode()
            status, msg_data = self.conn.uid(
                "FETCH", uid, "(FLAGS BODY.PEEK[])"
            )
            if status != "OK" or not msg_data or msg_data[0] is None:
                log.warning("Fetch failed for uid %s in %s", uid, self.email)
                continue
            flags = b" ".join(
                part for part in msg_data if isinstance(part, bytes)
            )
            raw = b""
            for part in msg_data:
                if isinstance(part, tuple) and len(part) >= 2:
                    if isinstance(part[0], bytes):
                        flags += part[0]
                    raw = part[1]
                    break
            if not raw:
                continue
            messages.append(
                parse_rfc822(
                    raw,
                    account_id=account_id,
                    folder=folder,
                    uid=uid,
                    is_read=b"\\Seen" in flags,
                    is_starred=b"\\Flagged" in flags,
                )
            )
        return messages

    def list_uids(self, folder: str, max_messages: int = 50) -> list[str]:
        if self._select_folder(folder, readonly=True) is None:
            return []
        status, data = self.conn.uid("SEARCH", None, "ALL")
        if status != "OK":
            return []
        return [u.decode() for u in data[0].split()[-max_messages:]]

    # --------------------------------------------------------------------- flags

    def _store(self, folder: str, uid: str, op: str, flag: str) -> None:
        if self._select_folder(folder, readonly=False) is None:
            raise ImapClientError(f"Folder '{folder}' not found on server")
        status, _ = self.conn.uid("STORE", uid, op, flag)
        if status != "OK":
            raise ImapClientError(f"IMAP STORE {op} {flag} failed for uid {uid}")

    def mark_read(self, folder: str, uid: str, read: bool = True) -> None:
        self._store(folder, uid, "+FLAGS" if read else "-FLAGS", "(\\Seen)")

    def set_starred(self, folder: str, uid: str, starred: bool) -> None:
        self._store(folder, uid, "+FLAGS" if starred else "-FLAGS", "(\\Flagged)")

    def move_to_trash(self, folder: str, uid: str) -> None:
        """Copy the message to the trash mailbox, then delete the original."""
        trash_name = None
        for name in FOLDER_CANDIDATES["trash"]:
            status, _ = self.conn.select(f'"{name}"', readonly=True)
            if status == "OK":
                trash_name = name
                break
        if self._select_folder(folder, readonly=False) is None:
            raise ImapClientError(f"Folder '{folder}' not found on server")
        if trash_name:
            self.conn.uid("COPY", uid, f'"{trash_name}"')
        self.conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        self.conn.expunge()

    # ---------------------------------------------------------------- append sent

    def append_to_sent(self, mime_bytes: bytes) -> None:
        """Best-effort: store a copy of an outgoing message in the Sent folder."""
        for name in FOLDER_CANDIDATES["sent"]:
            try:
                status, _ = self.conn.append(
                    f'"{name}"', "(\\Seen)", None, mime_bytes
                )
                if status == "OK":
                    return
            except imaplib.IMAP4.error:
                continue
        log.info("Could not append to a Sent folder for %s", self.email)


def verify_login(email_addr: str, password: str, host: str, port: int) -> None:
    """Try a full connect+login; raise ImapClientError with a friendly message."""
    try:
        conn = imaplib.IMAP4_SSL(host, port)
        conn.login(email_addr, password)
        conn.logout()
    except (imaplib.IMAP4.error, OSError) as e:
        raise ImapClientError(f"Could not sign in to {host}:{port}: {e}") from e

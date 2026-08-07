"""Background synchronization of all accounts into the local cache.

SyncWorker runs one full sync pass on a QThread. MainWindow owns a QTimer
that starts a pass every N minutes (and on manual refresh). Overlapping
passes are prevented by checking isRunning() before starting.

RemoteActionWorker applies user actions (mark read, star, trash) to the
server in the background so the UI never blocks on the network.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from app.database import Database
from app.email.gmail_client import GmailClient, GmailClientError
from app.email.imap_client import ImapClient, ImapClientError

log = logging.getLogger(__name__)

SYNC_FOLDERS = ("inbox", "sent", "trash")


class SyncWorker(QThread):
    progress = Signal(str)          # human-readable status line
    account_failed = Signal(str)    # "account@x: reason"
    finished_sync = Signal(int)     # number of newly arrived inbox messages

    def __init__(self, db_path: str, messages_per_folder: int = 50, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.messages_per_folder = messages_per_folder

    def run(self) -> None:
        # Fresh Database handle: sqlite connections must live on this thread.
        db = Database(self.db_path)
        new_inbox_total = 0
        try:
            accounts = db.get_accounts()
            for account in accounts:
                self.progress.emit(f"Syncing {account['email']}...")
                try:
                    if account["provider"] == "gmail":
                        new_inbox_total += self._sync_gmail(db, account)
                    else:
                        new_inbox_total += self._sync_imap(db, account)
                except (GmailClientError, ImapClientError, Exception) as e:
                    log.error("Sync failed for %s: %s", account["email"], e)
                    self.account_failed.emit(f"{account['email']}: {e}")
        finally:
            db.close()
        self.finished_sync.emit(new_inbox_total)

    # ---------------------------------------------------------------------- gmail

    def _sync_gmail(self, db: Database, account: dict) -> int:
        client = GmailClient(account["email"])
        new_inbox = 0
        for folder in SYNC_FOLDERS:
            ids = client.list_message_ids(folder, self.messages_per_folder)
            for msg_id in ids:
                if db.email_exists(account["id"], folder, msg_id):
                    # Refresh flags cheaply on existing messages is skipped for
                    # bandwidth; full body fetch happens only for new mail.
                    continue
                msg = client.fetch_message(msg_id, account["id"], folder)
                if db.upsert_email(msg) and folder == "inbox" and not msg["is_read"]:
                    new_inbox += 1
            db.replace_folder_uids(account["id"], folder, ids)
        return new_inbox

    # ----------------------------------------------------------------------- imap

    def _sync_imap(self, db: Database, account: dict) -> int:
        client = ImapClient(account)
        new_inbox = 0
        try:
            for folder in SYNC_FOLDERS:
                uids = client.list_uids(folder, self.messages_per_folder)
                new_uids = [
                    u for u in uids
                    if not db.email_exists(account["id"], folder, u)
                ]
                # Fetch bodies only for messages we do not have yet.
                if new_uids:
                    messages = client.fetch_folder(
                        folder, account["id"], self.messages_per_folder
                    )
                    for msg in messages:
                        if msg["uid"] not in new_uids:
                            continue
                        if (
                            db.upsert_email(msg)
                            and folder == "inbox"
                            and not msg["is_read"]
                        ):
                            new_inbox += 1
                db.replace_folder_uids(account["id"], folder, uids)
        finally:
            client.close()
        return new_inbox


class RemoteActionWorker(QThread):
    """Apply a single flag/trash action to the mail server in the background."""

    failed = Signal(str)

    def __init__(self, account: dict, action: str, uid: str, folder: str,
                 value: bool = True, parent=None):
        super().__init__(parent)
        self.account = account
        self.action = action  # 'read' | 'star' | 'trash'
        self.uid = uid
        self.folder = folder
        self.value = value

    def run(self) -> None:
        try:
            if self.account["provider"] == "gmail":
                client = GmailClient(self.account["email"])
                if self.action == "read":
                    client.mark_read(self.uid, self.value)
                elif self.action == "star":
                    client.set_starred(self.uid, self.value)
                elif self.action == "trash":
                    client.move_to_trash(self.uid)
            else:
                imap = ImapClient(self.account)
                try:
                    if self.action == "read":
                        imap.mark_read(self.folder, self.uid, self.value)
                    elif self.action == "star":
                        imap.set_starred(self.folder, self.uid, self.value)
                    elif self.action == "trash":
                        imap.move_to_trash(self.folder, self.uid)
                finally:
                    imap.close()
        except Exception as e:
            log.error("Remote %s failed for %s: %s",
                      self.action, self.account["email"], e)
            self.failed.emit(str(e))

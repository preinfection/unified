"""Background synchronization of all accounts into the local cache.

SyncWorker runs one full sync pass on a QThread. MainWindow owns a QTimer
that starts a pass every N minutes (and on manual refresh). Overlapping
passes are prevented by checking isRunning() before starting.

RemoteActionWorker applies user actions (mark read, star, trash) to the
server in the background so the UI never blocks on the network.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QThread, Signal

from app.database import Database
from app.email.gmail_client import GmailClient, GmailClientError
from app.email.imap_client import ImapClient, ImapClientError

log = logging.getLogger(__name__)

SYNC_FOLDERS = ("inbox", "sent", "trash")


def should_notify(account: dict, msg: dict, is_new: bool) -> bool:
    """Decide whether one synced message counts toward a new-mail notification.

    Messages downloaded during the initial import of an account are existing
    mail, not new mail - only accounts whose initial sync already completed
    can generate notifications, and only for newly inserted unread inbox
    messages that arrived after the last notification check.
    """
    if not is_new or msg["folder"] != "inbox" or msg["is_read"]:
        return False
    if not account.get("initial_sync_completed"):
        return False
    # Guard against re-notifying old mail that re-enters the cache (e.g. a
    # message moved back from another folder): its date must be newer than
    # the last completed check, with a day of slack for timezone drift.
    last_check = account.get("last_notification_check") or 0
    return msg["date_ts"] == 0 or msg["date_ts"] > last_check - 86400


class SyncWorker(QThread):
    progress = Signal(str)                    # status-bar text
    account_progress = Signal(int, str, int, int)  # account_id, detail, done, total
    account_finished = Signal(int, int, bool)      # account_id, imported, was_initial
    account_failed = Signal(str)              # "account@x: reason"
    finished_sync = Signal(int)               # unread messages to notify about

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path

    def run(self) -> None:
        # Fresh Database handle: sqlite connections must live on this thread.
        db = Database(self.db_path)
        notify_total = 0
        try:
            for account in db.get_accounts():
                initial = not account["initial_sync_completed"]
                self.progress.emit(
                    f"Syncing mailbox {account['email']}..."
                    if initial else f"Syncing {account['email']}..."
                )
                try:
                    if account["provider"] == "gmail":
                        imported, notify = self._sync_gmail(db, account)
                    else:
                        imported, notify = self._sync_imap(db, account)
                    now = int(time.time())
                    if initial:
                        db.mark_initial_sync_completed(account["id"], now)
                    db.set_last_notification_check(account["id"], now)
                    notify_total += notify
                    self.account_finished.emit(account["id"], imported, initial)
                except Exception as e:
                    log.error("Sync failed for %s: %s", account["email"], e)
                    self.account_failed.emit(f"{account['email']}: {e}")
        finally:
            db.close()
        self.finished_sync.emit(notify_total)

    # ---------------------------------------------------------------------- gmail

    def _sync_gmail(self, db: Database, account: dict) -> tuple[int, int]:
        """Full sync of one Gmail account. Returns (imported, notify_count)."""
        client = GmailClient(account["email"])
        account_id = account["id"]
        imported = 0
        notify = 0

        for folder in SYNC_FOLDERS:
            self.account_progress.emit(
                account_id, f"Fetching email list ({folder})...", 0, 0
            )
            # Complete id listing (paginated) - required both for full sync
            # and for correct pruning of server-side deletions.
            ids = client.list_all_message_ids(
                folder,
                on_page=lambda n, f=folder: self.account_progress.emit(
                    account_id, f"Fetching email list ({f}): {n} found...", 0, 0
                ),
            )
            new_ids = [
                i for i in ids if not db.email_exists(account_id, folder, i)
            ]
            total = len(new_ids)
            done = 0

            def on_message(msg: dict) -> None:
                nonlocal imported, notify, done
                is_new = db.upsert_email(msg)
                imported += 1 if is_new else 0
                if should_notify(account, msg, is_new):
                    notify += 1
                done += 1
                if done % 10 == 0 or done == total:
                    self.account_progress.emit(
                        account_id,
                        f"Downloading messages ({msg['folder']})...",
                        done,
                        total,
                    )

            if new_ids:
                client.fetch_messages(new_ids, account_id, folder, on_message)
            self.account_progress.emit(
                account_id, "Building local cache...", 1, 1
            )
            db.replace_folder_uids(account_id, folder, ids)

        self.account_progress.emit(account_id, "Updating unread counters...", 1, 1)
        return imported, notify

    # ----------------------------------------------------------------------- imap

    def _sync_imap(self, db: Database, account: dict) -> tuple[int, int]:
        """Full sync of one IMAP account. Returns (imported, notify_count)."""
        client = ImapClient(account)
        account_id = account["id"]
        imported = 0
        notify = 0
        try:
            for folder in SYNC_FOLDERS:
                self.account_progress.emit(
                    account_id, f"Fetching email list ({folder})...", 0, 0
                )
                uids = client.list_uids(folder)
                new_uids = [
                    u for u in uids
                    if not db.email_exists(account_id, folder, u)
                ]
                if new_uids and client.select_for_reading(folder):
                    total = len(new_uids)
                    # Newest first so the visible inbox fills immediately.
                    for done, uid in enumerate(reversed(new_uids), start=1):
                        msg = client.fetch_message(folder, uid, account_id)
                        if msg is None:
                            continue
                        is_new = db.upsert_email(msg)
                        imported += 1 if is_new else 0
                        if should_notify(account, msg, is_new):
                            notify += 1
                        if done % 5 == 0 or done == total:
                            self.account_progress.emit(
                                account_id,
                                f"Downloading messages ({folder})...",
                                done,
                                total,
                            )
                self.account_progress.emit(
                    account_id, "Building local cache...", 1, 1
                )
                db.replace_folder_uids(account_id, folder, uids)
        finally:
            client.close()
        self.account_progress.emit(account_id, "Updating unread counters...", 1, 1)
        return imported, notify


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

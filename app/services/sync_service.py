"""Background synchronization: per-account workers managed by SyncManager.

Design:
- One AccountSyncWorker (QThread) per account, up to MAX_PARALLEL at a time;
  the rest wait in a queue with visible "Waiting" status. The UI thread never
  does network or bulk-database work, so the app stays usable during sync.
- Sync is metadata-first: headers/flags/snippets are downloaded in large
  batches; message bodies are fetched on demand when an email is opened
  (BodyFetchWorker). This is what makes 15k-message mailboxes import fast.
- Results are verified, not assumed: after each folder the local row count is
  compared against the server id list. "Mailbox ready" is only reported when
  they match; otherwise the result carries an honest failed count and the
  next sync retries the missing messages automatically.

RemoteActionWorker applies user actions (read/star/trash) server-side in the
background.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QThread, Signal

from app.database import Database
from app.email.gmail_client import GmailClient, GmailClientError
from app.email.imap_client import ImapClient, ImapClientError

log = logging.getLogger(__name__)

SYNC_FOLDERS = ("inbox", "sent", "trash")

# Account status vocabulary
ST_IDLE = "idle"
ST_WAITING = "waiting"
ST_SYNCING = "syncing"
ST_DONE = "done"          # verified complete
ST_PARTIAL = "partial"    # finished with failed messages
ST_ERROR = "error"
ST_CANCELLED = "cancelled"

# Phases within ST_SYNCING - a strict, visible state machine
PH_CONNECT = "Connecting"
PH_LIST = "Downloading message list"
PH_META = "Syncing metadata"
PH_BODIES = "Downloading missing bodies"
PH_INDEX = "Indexing"
PH_VERIFY = "Verifying"

# How many recent inbox messages get their bodies pre-downloaded per sync,
# so opening them is instant and works offline.
BODY_BACKFILL_LIMIT = 200


def friendly_error(e: Exception) -> str:
    """Turn raw client errors into messages a user can act on."""
    text = str(e)
    if "Too many concurrent requests" in text or "rateLimitExceeded" in text \
            or "429" in text:
        return ("Gmail API rate limit reached - the app backs off and retries "
                "automatically on the next sync")
    if "invalid_grant" in text or "credentials" in text.lower():
        return "Sign-in expired - remove and re-add this account"
    if "getaddrinfo" in text or "timed out" in text or "Network" in text:
        return "Network unreachable - check your connection"
    return text


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
    last_check = account.get("last_notification_check") or 0
    return msg["date_ts"] == 0 or msg["date_ts"] > last_check - 86400


class AccountSyncWorker(QThread):
    """Synchronizes one account through an explicit phase state machine:

    Connecting -> per folder (Downloading message list -> Syncing metadata ->
    Indexing) -> Downloading missing bodies -> Verifying -> done.
    """

    progress = Signal(int, str, int, int)   # account_id, phase, done, total
    result_ready = Signal(int, dict)        # account_id, result dict

    FLUSH_SIZE = 200  # messages per database transaction

    def __init__(self, db_path: str, account_id: int, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.account_id = account_id
        self._stop = False

    def request_stop(self) -> None:
        self._stop = True

    def _stopped(self) -> bool:
        return self._stop

    def run(self) -> None:
        db = Database(self.db_path)
        result = {
            "imported": 0, "notify": 0, "failed": 0,
            "server_total": 0, "local_total": 0,
            "was_initial": False, "error": "", "cancelled": False,
        }
        try:
            account = db.get_account(self.account_id)
            if account is None:
                result["error"] = "account removed"
                return
            result["was_initial"] = not account["initial_sync_completed"]
            log.info("Account %s: sync started", account["id"])
            self.progress.emit(account["id"], PH_CONNECT, 0, 0)
            if account["provider"] == "gmail":
                folder_counts = self._sync_gmail(db, account, result)
            else:
                folder_counts = self._sync_imap(db, account, result)
            if self._stopped():
                result["cancelled"] = True
                log.info("Account %s: sync cancelled", account["id"])
                return

            # ---- Verifying: never claim complete without matching counts.
            self.progress.emit(account["id"], PH_VERIFY, 0, 0)
            for folder, server_count in folder_counts.items():
                local = db.count_emails(folder=folder, account_id=account["id"])
                result["server_total"] += server_count
                result["local_total"] += local
                result["failed"] += max(0, server_count - local)
            now = int(time.time())
            log.info(
                "Account %s: verify - server %d, local %d, failed %d",
                account["id"], result["server_total"],
                result["local_total"], result["failed"],
            )
            if result["failed"] == 0 and result["was_initial"]:
                db.mark_initial_sync_completed(account["id"], now)
            db.set_last_notification_check(account["id"], now)
            log.info("Account %s: sync finished (%d imported, %d failed)",
                     account["id"], result["imported"], result["failed"])
        except Exception as e:
            reason = friendly_error(e)
            log.error("Sync failed for account %s: %s", self.account_id, reason)
            result["error"] = reason
        finally:
            db.close()
            self.result_ready.emit(self.account_id, result)

    # ---------------------------------------------------------------- helpers

    def _flush(self, db: Database, account: dict, batch: list[dict],
               result: dict, count_import: bool = True) -> None:
        if not batch:
            return
        db.upsert_emails(batch)
        if count_import:
            result["imported"] += len(batch)
            for msg in batch:
                if should_notify(account, msg, True):
                    result["notify"] += 1
        batch.clear()

    # ------------------------------------------------------------------ gmail

    def _sync_gmail(self, db: Database, account: dict, result: dict) -> dict:
        client = GmailClient(account["email"])
        aid = account["id"]
        folder_counts: dict[str, int] = {}
        for folder in SYNC_FOLDERS:
            if self._stopped():
                return folder_counts
            self.progress.emit(aid, PH_LIST, 0, 0)
            ids = client.list_all_message_ids(
                folder,
                on_page=lambda n, f=folder: (
                    log.info("Account %s: %s list - %d ids so far",
                             aid, f, n),
                    self.progress.emit(aid, PH_LIST, n, 0),
                ),
            )
            folder_counts[folder] = len(ids)
            existing = set(db.get_folder_uids(aid, folder))
            new_ids = [i for i in ids if i not in existing]
            total = len(new_ids)
            log.info("Account %s: %s - %d on server, %d new",
                     aid, folder, len(ids), total)

            done = 0
            pending: list[dict] = []

            def on_message(msg: dict) -> None:
                nonlocal done
                pending.append(msg)
                done += 1
                if len(pending) >= self.FLUSH_SIZE:
                    self._flush(db, account, pending, result)
                if done % 50 == 0 or done == total:
                    self.progress.emit(aid, PH_META, done, total)

            failed_ids = client.fetch_metadata(
                new_ids, aid, folder, on_message, should_stop=self._stopped
            ) if new_ids else []
            self._flush(db, account, pending, result)
            if self._stopped():
                return folder_counts

            self.progress.emit(aid, PH_INDEX, 0, 0)
            db.replace_folder_uids(aid, folder, ids)
            if failed_ids:
                log.warning("Account %s: %s - %d messages failed to download",
                            aid, folder, len(failed_ids))

        self._backfill_gmail_bodies(db, client, account)
        return folder_counts

    def _backfill_gmail_bodies(self, db: Database, client: GmailClient,
                               account: dict) -> None:
        """Pre-download bodies for the newest inbox messages still missing one."""
        aid = account["id"]
        uids = db.get_missing_body_uids(aid, "inbox", BODY_BACKFILL_LIMIT)
        if not uids or self._stopped():
            return
        log.info("Account %s: downloading %d missing bodies", aid, len(uids))
        total = len(uids)
        done = 0
        pending: list[dict] = []

        def on_message(msg: dict) -> None:
            nonlocal done
            pending.append(msg)
            done += 1
            if len(pending) >= 50:
                db.upsert_emails(pending)
                pending.clear()
            if done % 20 == 0 or done == total:
                self.progress.emit(aid, PH_BODIES, done, total)

        self.progress.emit(aid, PH_BODIES, 0, total)
        # Failures are fine here: bodies still load on demand when opened.
        client.fetch_bodies(uids, aid, "inbox", on_message,
                            should_stop=self._stopped)
        db.upsert_emails(pending)

    # ------------------------------------------------------------------- imap

    def _sync_imap(self, db: Database, account: dict, result: dict) -> dict:
        client = ImapClient(account)
        aid = account["id"]
        folder_counts: dict[str, int] = {}
        try:
            for folder in SYNC_FOLDERS:
                if self._stopped():
                    return folder_counts
                self.progress.emit(aid, PH_LIST, 0, 0)
                uids = client.list_uids(folder)
                folder_counts[folder] = len(uids)
                existing = set(db.get_folder_uids(aid, folder))
                new_uids = [u for u in uids if u not in existing]
                total = len(new_uids)
                log.info("Account %s: %s - %d on server, %d new",
                         aid, folder, len(uids), total)

                pending: list[dict] = []
                if new_uids and client.select_for_reading(folder):
                    # Newest first so the visible inbox fills immediately.
                    for done, uid in enumerate(reversed(new_uids), start=1):
                        if self._stopped():
                            self._flush(db, account, pending, result)
                            return folder_counts
                        msg = client.fetch_headers(folder, uid, aid)
                        if msg is not None:
                            pending.append(msg)
                        if len(pending) >= self.FLUSH_SIZE:
                            self._flush(db, account, pending, result)
                        if done % 20 == 0 or done == total:
                            self.progress.emit(aid, PH_META, done, total)
                self._flush(db, account, pending, result)
                self.progress.emit(aid, PH_INDEX, 0, 0)
                db.replace_folder_uids(aid, folder, uids)

            # Body backfill for the newest inbox messages (smaller cap: IMAP
            # fetches are sequential).
            uids = db.get_missing_body_uids(aid, "inbox", 50)
            if uids and client.select_for_reading("inbox"):
                total = len(uids)
                self.progress.emit(aid, PH_BODIES, 0, total)
                pending = []
                for done, uid in enumerate(uids, start=1):
                    if self._stopped():
                        break
                    msg = client.fetch_message("inbox", uid, aid)
                    if msg is not None:
                        pending.append(msg)
                    if done % 10 == 0 or done == total:
                        self.progress.emit(aid, PH_BODIES, done, total)
                db.upsert_emails(pending)
        finally:
            client.close()
        return folder_counts


class SyncManager(QObject):
    """Runs account sync workers with a small parallelism cap and a queue.

    Lives on the UI thread; all signals are delivered there. Adding an
    account mid-sync just enqueues it ("Waiting" in the sidebar) - nothing
    ever blocks the UI.
    """

    MAX_PARALLEL = 2

    state_changed = Signal(int)             # account_id
    progress = Signal(int, str, int, int)   # account_id, phase, done, total
    account_done = Signal(int, dict)        # account_id, result
    all_finished = Signal(int)              # total notify count for this round

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self._workers: dict[int, AccountSyncWorker] = {}
        self._queue: list[int] = []
        self._states: dict[int, dict] = {}
        self._notify_accum = 0

    # ------------------------------------------------------------------ state

    def status(self, account_id: int) -> dict:
        return self._states.get(account_id, {"status": ST_IDLE})

    def is_busy(self) -> bool:
        return bool(self._workers or self._queue)

    def is_account_pending(self, account_id: int) -> bool:
        return self.status(account_id)["status"] in (ST_WAITING, ST_SYNCING)

    def known_account_ids(self) -> list[int]:
        return list(self._states.keys())

    def _set_state(self, account_id: int, status: str, **extra) -> None:
        self._states[account_id] = {"status": status, **extra}
        self.state_changed.emit(account_id)

    # ---------------------------------------------------------------- control

    def request_sync(self, account_ids: list[int]) -> None:
        for aid in account_ids:
            if aid in self._workers or aid in self._queue:
                continue
            self._queue.append(aid)
            self._set_state(aid, ST_WAITING)
        self._pump()

    def forget_account(self, account_id: int) -> None:
        """Drop a removed account from queue/state (running worker finishes)."""
        if account_id in self._queue:
            self._queue.remove(account_id)
        self._states.pop(account_id, None)

    def shutdown(self, wait_ms: int = 5000) -> None:
        self._queue.clear()
        for worker in self._workers.values():
            worker.request_stop()
        for worker in list(self._workers.values()):
            worker.wait(wait_ms)
        self._workers.clear()

    def _pump(self) -> None:
        while self._queue and len(self._workers) < self.MAX_PARALLEL:
            aid = self._queue.pop(0)
            worker = AccountSyncWorker(self.db_path, aid, self)
            worker.progress.connect(self._on_progress)
            worker.result_ready.connect(self._on_result)
            self._workers[aid] = worker
            self._set_state(aid, ST_SYNCING, phase=PH_CONNECT, done=0, total=0)
            worker.start()

    # ---------------------------------------------------------------- signals

    def _on_progress(self, account_id: int, phase: str, done: int, total: int) -> None:
        state = self._states.get(account_id)
        if state is not None:
            state.update(phase=phase, done=done, total=total)
        self.progress.emit(account_id, phase, done, total)

    def _on_result(self, account_id: int, result: dict) -> None:
        worker = self._workers.pop(account_id, None)
        if worker is not None:
            worker.deleteLater()
        if result.get("error"):
            self._set_state(account_id, ST_ERROR, result=result)
        elif result.get("cancelled"):
            self._set_state(account_id, ST_CANCELLED, result=result)
        elif result.get("failed"):
            self._set_state(account_id, ST_PARTIAL, result=result)
        else:
            self._set_state(account_id, ST_DONE, result=result)
        self._notify_accum += result.get("notify", 0)
        self.account_done.emit(account_id, result)
        self._pump()
        if not self.is_busy():
            notify = self._notify_accum
            self._notify_accum = 0
            self.all_finished.emit(notify)


class BodyFetchWorker(QThread):
    """Downloads one message body on demand (when the user opens the email)."""

    loaded = Signal(int)          # email row id
    failed = Signal(int, str)     # email row id, reason

    def __init__(self, db_path: str, email_row: dict, account: dict, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.email_row = email_row
        self.account = account

    def run(self) -> None:
        row = self.email_row
        db = Database(self.db_path)
        try:
            if self.account["provider"] == "gmail":
                client = GmailClient(self.account["email"])
                msg = client.fetch_message(row["uid"], row["account_id"],
                                           row["folder"])
            else:
                imap = ImapClient(self.account)
                try:
                    if not imap.select_for_reading(row["folder"]):
                        raise ImapClientError(
                            f"Folder '{row['folder']}' not found"
                        )
                    msg = imap.fetch_message(row["folder"], row["uid"],
                                             row["account_id"])
                finally:
                    imap.close()
            if msg is None:
                raise GmailClientError("Message no longer exists on the server")
            db.update_body(
                row["id"], msg["body_text"], msg["body_html"],
                bool(msg["has_attachments"]),
            )
            self.loaded.emit(row["id"])
        except Exception as e:
            log.error("Body fetch failed for email %s: %s", row.get("id"), e)
            self.failed.emit(row["id"], str(e))
        finally:
            db.close()


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
            log.error("Remote %s failed for account %s: %s",
                      self.action, self.account["id"], e)
            self.failed.emit(str(e))

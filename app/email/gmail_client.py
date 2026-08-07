"""Gmail API client for one account: fetch, flag, trash, and send messages."""

from __future__ import annotations

import base64
import logging
import time
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.auth import gmail_oauth
from app.email.message_parser import make_snippet

log = logging.getLogger(__name__)

# App folder name -> Gmail label
FOLDER_LABELS = {"inbox": "INBOX", "sent": "SENT", "trash": "TRASH"}


class GmailClientError(Exception):
    pass


class GmailClient:
    def __init__(self, email_address: str):
        self.email = email_address
        creds = gmail_oauth.load_credentials(email_address)
        if creds is None:
            raise GmailClientError(
                "No valid Gmail credentials for this account; re-add it."
            )
        # cache_discovery=False avoids oauth2client-era file cache warnings.
        self.service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    # ------------------------------------------------------------------ fetching

    def list_all_message_ids(self, folder: str, on_page=None) -> list[str]:
        """Return every message id in a folder, newest first, via pagination.

        on_page(count_so_far) is called after each page for progress display.
        """
        label = FOLDER_LABELS[folder]
        ids: list[str] = []
        page_token: str | None = None
        while True:
            try:
                resp = (
                    self.service.users()
                    .messages()
                    .list(
                        userId="me",
                        labelIds=[label],
                        maxResults=500,
                        pageToken=page_token,
                    )
                    .execute()
                )
            except HttpError as e:
                raise GmailClientError(f"Gmail list failed: {e}") from e
            ids.extend(m["id"] for m in resp.get("messages", []))
            if on_page:
                on_page(len(ids))
            page_token = resp.get("nextPageToken")
            if not page_token:
                return ids

    def fetch_metadata(
        self,
        msg_ids: list[str],
        account_id: int,
        folder: str,
        on_message,
        should_stop=None,
    ) -> list[str]:
        """Fetch message metadata (headers/flags/snippet, no bodies) in batches.

        Calls on_message(dict) per message and returns the ids that still
        failed after retries, so the caller reports an honest sync result.
        Gmail throttles concurrent requests ("Too many concurrent requests
        for user", 429), so failed ids are retried in additional passes with
        increasing backoff and smaller batches.
        """
        failed = self._fetch_metadata_pass(
            msg_ids, account_id, folder, on_message, 25, should_stop
        )
        for delay, batch_size in ((2, 15), (5, 10)):
            if not failed or (should_stop is not None and should_stop()):
                break
            log.info("Retrying %d rate-limited messages in %ds (batch %d)",
                     len(failed), delay, batch_size)
            time.sleep(delay)
            failed = self._fetch_metadata_pass(
                failed, account_id, folder, on_message, batch_size, should_stop
            )
        return failed

    def _fetch_metadata_pass(
        self,
        msg_ids: list[str],
        account_id: int,
        folder: str,
        on_message,
        batch_size: int,
        should_stop=None,
    ) -> list[str]:
        failed: list[str] = []

        def _callback(request_id, response, exception) -> None:
            if exception is not None:
                log.warning("Gmail metadata fetch failed for %s: %s",
                            request_id, exception)
                failed.append(request_id)
                return
            on_message(self._to_metadata_dict(response, account_id, folder))

        for start in range(0, len(msg_ids), batch_size):
            if should_stop is not None and should_stop():
                failed.extend(msg_ids[start:])
                return failed
            chunk = msg_ids[start:start + batch_size]
            batch = self.service.new_batch_http_request(callback=_callback)
            for msg_id in chunk:
                batch.add(
                    self.service.users().messages().get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["From", "To", "Subject", "Date"],
                    ),
                    request_id=msg_id,
                )
            try:
                self._execute_with_retry(batch)
            except HttpError as e:
                log.error("Gmail batch failed after retries: %s", e)
                failed.extend(chunk)
            # Brief pacing between batches keeps Gmail's per-user concurrency
            # limiter (429 "Too many concurrent requests") mostly quiet.
            time.sleep(0.1)
        return failed

    def fetch_bodies(
        self,
        msg_ids: list[str],
        account_id: int,
        folder: str,
        on_message,
        should_stop=None,
    ) -> list[str]:
        """Fetch full messages (bodies) in small paced batches; returns failed ids.

        Used to backfill bodies for recent messages after the metadata sync,
        so opening them is instant and works offline.
        """
        failed: list[str] = []

        def _callback(request_id, response, exception) -> None:
            if exception is not None:
                log.warning("Gmail body fetch failed for %s: %s",
                            request_id, exception)
                failed.append(request_id)
                return
            on_message(self._to_message_dict(response, account_id, folder))

        batch_size = 10  # full bodies are heavy; keep concurrency low
        for start in range(0, len(msg_ids), batch_size):
            if should_stop is not None and should_stop():
                failed.extend(msg_ids[start:])
                return failed
            chunk = msg_ids[start:start + batch_size]
            batch = self.service.new_batch_http_request(callback=_callback)
            for msg_id in chunk:
                batch.add(
                    self.service.users().messages().get(
                        userId="me", id=msg_id, format="full"
                    ),
                    request_id=msg_id,
                )
            try:
                self._execute_with_retry(batch)
            except HttpError as e:
                log.error("Gmail body batch failed after retries: %s", e)
                failed.extend(chunk)
            time.sleep(0.1)
        return failed

    @staticmethod
    def _execute_with_retry(batch, attempts: int = 3) -> None:
        for attempt in range(attempts):
            try:
                batch.execute()
                return
            except HttpError as e:
                status = getattr(e.resp, "status", 0)
                if status in (429, 500, 502, 503) and attempt < attempts - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

    def _to_metadata_dict(self, data: dict, account_id: int, folder: str) -> dict:
        headers = {
            h["name"].lower(): h["value"]
            for h in data.get("payload", {}).get("headers", [])
        }
        labels = set(data.get("labelIds", []))

        import email.utils as eut

        sender_name, sender_email = eut.parseaddr(headers.get("from", ""))
        return {
            "account_id": account_id,
            "uid": data["id"],
            "folder": folder,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "recipients": headers.get("to", ""),
            "subject": headers.get("subject", ""),
            "snippet": data.get("snippet", ""),
            "body_text": "",
            "body_html": "",
            "date_ts": int(int(data.get("internalDate", 0)) / 1000),
            "is_read": 0 if "UNREAD" in labels else 1,
            "is_starred": 1 if "STARRED" in labels else 0,
            "has_attachments": 0,
            "body_fetched": 0,
        }

    def fetch_message(self, msg_id: str, account_id: int, folder: str) -> dict:
        for attempt in range(3):
            try:
                data = (
                    self.service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )
                return self._to_message_dict(data, account_id, folder)
            except HttpError as e:
                status = getattr(e.resp, "status", 0)
                if status in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(1 + attempt)
                    continue
                raise GmailClientError(f"Gmail fetch failed: {e}") from e

    def _to_message_dict(self, data: dict, account_id: int, folder: str) -> dict:
        headers = {
            h["name"].lower(): h["value"]
            for h in data.get("payload", {}).get("headers", [])
        }
        labels = set(data.get("labelIds", []))

        import email.utils as eut

        sender_name, sender_email = eut.parseaddr(headers.get("from", ""))
        date_ts = int(int(data.get("internalDate", 0)) / 1000)

        body_text, body_html, has_attachments = self._walk_payload(
            data.get("payload", {}), data["id"]
        )

        return {
            "account_id": account_id,
            "uid": data["id"],
            "folder": folder,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "recipients": headers.get("to", ""),
            "subject": headers.get("subject", ""),
            "snippet": data.get("snippet", "") or make_snippet(body_text, body_html),
            "body_text": body_text,
            "body_html": body_html,
            "date_ts": date_ts,
            "is_read": 0 if "UNREAD" in labels else 1,
            "is_starred": 1 if "STARRED" in labels else 0,
            "has_attachments": 1 if has_attachments else 0,
            "body_fetched": 1,
        }

    def _walk_payload(self, payload: dict, msg_id: str) -> tuple[str, str, bool]:
        """Recursively extract text/html bodies and attachment presence."""
        body_text, body_html = "", ""
        has_attachments = False

        def decode(body: dict) -> str:
            data = body.get("data", "")
            if data:
                return base64.urlsafe_b64decode(data.encode()).decode(
                    "utf-8", errors="replace"
                )
            # Large bodies are sometimes delivered as attachments instead of
            # inline data - fetch them, or the preview would be blank.
            att_id = body.get("attachmentId")
            if att_id:
                try:
                    att = (
                        self.service.users().messages().attachments()
                        .get(userId="me", messageId=msg_id, id=att_id)
                        .execute()
                    )
                    return base64.urlsafe_b64decode(
                        att.get("data", "").encode()
                    ).decode("utf-8", errors="replace")
                except HttpError as e:
                    log.warning("Attachment-hosted body fetch failed: %s", e)
            return ""

        def walk(part: dict) -> None:
            nonlocal body_text, body_html, has_attachments
            mime = part.get("mimeType", "")
            if part.get("filename"):
                has_attachments = True
                return
            if mime == "text/plain" and not body_text:
                body_text = decode(part.get("body", {}))
            elif mime == "text/html" and not body_html:
                body_html = decode(part.get("body", {}))
            for sub in part.get("parts", []) or []:
                walk(sub)

        walk(payload)
        return body_text, body_html, has_attachments

    # --------------------------------------------------------------------- flags

    def mark_read(self, msg_id: str, read: bool = True) -> None:
        body = (
            {"removeLabelIds": ["UNREAD"]} if read else {"addLabelIds": ["UNREAD"]}
        )
        self._modify(msg_id, body)

    def set_starred(self, msg_id: str, starred: bool) -> None:
        body = (
            {"addLabelIds": ["STARRED"]} if starred else {"removeLabelIds": ["STARRED"]}
        )
        self._modify(msg_id, body)

    def _modify(self, msg_id: str, body: dict) -> None:
        try:
            self.service.users().messages().modify(
                userId="me", id=msg_id, body=body
            ).execute()
        except HttpError as e:
            raise GmailClientError(f"Gmail modify failed: {e}") from e

    def move_to_trash(self, msg_id: str) -> None:
        try:
            self.service.users().messages().trash(userId="me", id=msg_id).execute()
        except HttpError as e:
            raise GmailClientError(f"Gmail trash failed: {e}") from e

    # ------------------------------------------------------------------- sending

    def send(self, to: str, subject: str, body: str) -> None:
        mime = MIMEText(body, "plain", "utf-8")
        mime["To"] = to
        mime["From"] = self.email
        mime["Subject"] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        try:
            self.service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
        except HttpError as e:
            raise GmailClientError(f"Gmail send failed: {e}") from e

    @staticmethod
    def profile_email(credentials) -> str:
        """Return the address of the account the credentials belong to."""
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        return profile["emailAddress"]

"""Gmail API client for one account: fetch, flag, trash, and send messages."""

from __future__ import annotations

import base64
import logging
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
                f"No valid Gmail credentials for {email_address}; re-add the account."
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

    def fetch_messages(
        self,
        msg_ids: list[str],
        account_id: int,
        folder: str,
        on_message,
        batch_size: int = 40,
    ) -> None:
        """Fetch full messages in batched API calls; on_message(dict) per message.

        Batching cuts round-trips ~40x, which matters for initial imports of
        large mailboxes. Individual failures are logged and skipped so one bad
        message never aborts the sync.
        """

        def _callback(request_id, response, exception) -> None:
            if exception is not None:
                log.warning("Gmail fetch failed for one message: %s", exception)
                return
            on_message(self._to_message_dict(response, account_id, folder))

        for start in range(0, len(msg_ids), batch_size):
            chunk = msg_ids[start:start + batch_size]
            try:
                batch = self.service.new_batch_http_request(callback=_callback)
                for msg_id in chunk:
                    batch.add(
                        self.service.users()
                        .messages()
                        .get(userId="me", id=msg_id, format="full")
                    )
                batch.execute()
            except HttpError as e:
                raise GmailClientError(f"Gmail batch fetch failed: {e}") from e

    def fetch_message(self, msg_id: str, account_id: int, folder: str) -> dict:
        try:
            data = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
        except HttpError as e:
            raise GmailClientError(f"Gmail fetch failed: {e}") from e
        return self._to_message_dict(data, account_id, folder)

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
            data.get("payload", {})
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
        }

    def _walk_payload(self, payload: dict) -> tuple[str, str, bool]:
        """Recursively extract text/html bodies and attachment presence."""
        body_text, body_html = "", ""
        has_attachments = False

        def decode(body: dict) -> str:
            data = body.get("data", "")
            if not data:
                return ""
            return base64.urlsafe_b64decode(data.encode()).decode(
                "utf-8", errors="replace"
            )

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

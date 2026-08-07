"""Parse raw RFC 822 messages (from IMAP) into the app's message dict shape."""

from __future__ import annotations

import email
import email.header
import email.utils
import logging
import re
from email.message import Message

log = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")
_TAGS = re.compile(r"<[^>]+>")


def decode_header_value(value: str) -> str:
    """Decode MIME-encoded header words (=?utf-8?...?=) to a plain string."""
    if not value:
        return ""
    parts = []
    for chunk, charset in email.header.decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _payload_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:  # unknown charset name
        return payload.decode("utf-8", errors="replace")


def extract_bodies(msg: Message) -> tuple[str, str, bool]:
    """Return (body_text, body_html, has_attachments) from a parsed message."""
    body_text, body_html = "", ""
    has_attachments = False
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        ctype = part.get_content_type()
        disposition = str(part.get("Content-Disposition") or "")
        if part.get_filename() or "attachment" in disposition.lower():
            has_attachments = True
            continue
        if ctype == "text/plain" and not body_text:
            body_text = _payload_text(part)
        elif ctype == "text/html" and not body_html:
            body_html = _payload_text(part)
    return body_text, body_html, has_attachments


def make_snippet(body_text: str, body_html: str, length: int = 160) -> str:
    text = body_text or _TAGS.sub(" ", body_html)
    return _WHITESPACE.sub(" ", text).strip()[:length]


def parse_rfc822(raw: bytes, account_id: int, folder: str, uid: str,
                 is_read: bool = False, is_starred: bool = False) -> dict:
    """Parse raw message bytes into the dict shape Database.upsert_email expects."""
    msg = email.message_from_bytes(raw)

    sender_name, sender_email = email.utils.parseaddr(
        decode_header_value(msg.get("From", ""))
    )
    recipients = decode_header_value(msg.get("To", ""))
    subject = decode_header_value(msg.get("Subject", ""))

    date_ts = 0
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date", ""))
        if dt is not None:
            date_ts = int(dt.timestamp())
    except (TypeError, ValueError):
        log.debug("Unparseable date header: %r", msg.get("Date"))

    body_text, body_html, has_attachments = extract_bodies(msg)

    return {
        "account_id": account_id,
        "uid": uid,
        "folder": folder,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "recipients": recipients,
        "subject": subject,
        "snippet": make_snippet(body_text, body_html),
        "body_text": body_text,
        "body_html": body_html,
        "date_ts": date_ts,
        "is_read": 1 if is_read else 0,
        "is_starred": 1 if is_starred else 0,
        "has_attachments": 1 if has_attachments else 0,
    }

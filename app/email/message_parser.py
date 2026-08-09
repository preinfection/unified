"""Parse raw RFC 822 messages (from IMAP) into the app's message dict shape."""

from __future__ import annotations

import base64
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


_CID_SRC = re.compile(
    r'((?:src|background)\s*=\s*["\'])cid:([^"\']+)(["\'])', re.IGNORECASE
)


def resolve_cid_images(html: str, cid_map: dict[str, tuple[bytes, str]]) -> str:
    """Replace src="cid:xxx" references with inline data: URIs.

    QTextBrowser has no notion of a MIME message's Content-ID parts (that's
    an email concept, not an HTML one), so cid: URLs are otherwise dead
    references - the image silently never appears. cid_map is keyed by the
    Content-ID with angle brackets stripped, matching the img tag's raw
    "cid:<the same id>" reference.
    """
    if not html or not cid_map:
        return html

    def _sub(m: re.Match) -> str:
        content_id = m.group(2).strip()
        found = cid_map.get(content_id)
        if not found:
            return m.group(0)
        data, mime = found
        b64 = base64.b64encode(data).decode("ascii")
        return f"{m.group(1)}data:{mime};base64,{b64}{m.group(3)}"

    return _CID_SRC.sub(_sub, html)


def extract_bodies(msg: Message) -> tuple[str, str, bool]:
    """Return (body_text, body_html, has_attachments) from a parsed message.

    Inline images referenced by the HTML as cid:<Content-ID> are resolved
    into data: URIs before body_html is returned - see resolve_cid_images.
    """
    body_text, body_html = "", ""
    has_attachments = False
    cid_map: dict[str, tuple[bytes, str]] = {}
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        ctype = part.get_content_type()
        content_id = (part.get("Content-ID") or "").strip().strip("<>")
        if content_id and ctype.startswith("image/"):
            payload = part.get_payload(decode=True)
            if payload:
                cid_map[content_id] = (payload, ctype)
        disposition = str(part.get("Content-Disposition") or "")
        if part.get_filename() or "attachment" in disposition.lower():
            has_attachments = True
            continue
        if ctype == "text/plain" and not body_text:
            body_text = _payload_text(part)
        elif ctype == "text/html" and not body_html:
            body_html = _payload_text(part)
    body_html = resolve_cid_images(body_html, cid_map)
    return body_text, body_html, has_attachments


def make_snippet(body_text: str, body_html: str, length: int = 160) -> str:
    text = body_text or _TAGS.sub(" ", body_html)
    return _WHITESPACE.sub(" ", text).strip()[:length]


def _header_fields(msg: Message) -> dict:
    sender_name, sender_email = email.utils.parseaddr(
        decode_header_value(msg.get("From", ""))
    )
    date_ts = 0
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date", ""))
        if dt is not None:
            date_ts = int(dt.timestamp())
    except (TypeError, ValueError):
        log.debug("Unparseable date header: %r", msg.get("Date"))
    return {
        "sender_name": sender_name,
        "sender_email": sender_email,
        "recipients": decode_header_value(msg.get("To", "")),
        "subject": decode_header_value(msg.get("Subject", "")),
        "date_ts": date_ts,
    }


def parse_rfc822(raw: bytes, account_id: int, folder: str, uid: str,
                 is_read: bool = False, is_starred: bool = False) -> dict:
    """Parse full raw message bytes into the Database.upsert_email dict shape."""
    msg = email.message_from_bytes(raw)
    body_text, body_html, has_attachments = extract_bodies(msg)

    return {
        "account_id": account_id,
        "uid": uid,
        "folder": folder,
        **_header_fields(msg),
        "snippet": make_snippet(body_text, body_html),
        "body_text": body_text,
        "body_html": body_html,
        "is_read": 1 if is_read else 0,
        "is_starred": 1 if is_starred else 0,
        "has_attachments": 1 if has_attachments else 0,
        "body_fetched": 1,
    }


def parse_headers(raw_headers: bytes, account_id: int, folder: str, uid: str,
                  is_read: bool = False, is_starred: bool = False) -> dict:
    """Parse a headers-only fetch (metadata-first sync; body loads on demand)."""
    msg = email.message_from_bytes(raw_headers)
    return {
        "account_id": account_id,
        "uid": uid,
        "folder": folder,
        **_header_fields(msg),
        "snippet": "",
        "body_text": "",
        "body_html": "",
        "is_read": 1 if is_read else 0,
        "is_starred": 1 if is_starred else 0,
        "has_attachments": 0,
        "body_fetched": 0,
    }

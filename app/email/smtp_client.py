"""SMTP sending for IMAP accounts (SSL or STARTTLS, password from keyring)."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from app.auth import secrets_store

log = logging.getLogger(__name__)


class SmtpError(Exception):
    pass


def split_addresses(value: str) -> list[str]:
    return [addr.strip() for addr in (value or "").split(",") if addr.strip()]


def build_mime(sender: str, to: str, subject: str, body: str,
               cc: str = "", bcc: str = "") -> MIMEText:
    mime = MIMEText(body, "plain", "utf-8")
    mime["From"] = sender
    mime["To"] = to
    if cc:
        mime["Cc"] = cc
    # Bcc is deliberately NOT written into the MIME headers - it is passed
    # to sendmail as an envelope recipient only. A Bcc header would be
    # delivered to every recipient, which is the exact opposite of what
    # blind copy means.
    mime["Subject"] = subject
    return mime


def send_message(account: dict, to: str, subject: str, body: str,
                 cc: str = "", bcc: str = "") -> bytes:
    """Send a plain-text message; returns the raw MIME bytes that were sent."""
    sender = account["email"]
    password = secrets_store.get_secret(secrets_store.KIND_IMAP_PASSWORD, sender)
    if not password:
        raise SmtpError(f"No stored password for {sender}; re-add the account.")

    host = account["smtp_host"]
    port = int(account["smtp_port"] or 587)
    mime = build_mime(sender, to, subject, body, cc, bcc)
    envelope = split_addresses(to) + split_addresses(cc) + split_addresses(bcc)

    try:
        if port == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        with server:
            server.login(sender, password)
            server.sendmail(sender, envelope, mime.as_bytes())
    except (smtplib.SMTPException, OSError) as e:
        raise SmtpError(f"Sending via {host}:{port} failed: {e}") from e
    return mime.as_bytes()

"""SMTP sending for IMAP accounts (SSL or STARTTLS, password from keyring)."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from app.auth import secrets_store

log = logging.getLogger(__name__)


class SmtpError(Exception):
    pass


def build_mime(sender: str, to: str, subject: str, body: str) -> MIMEText:
    mime = MIMEText(body, "plain", "utf-8")
    mime["From"] = sender
    mime["To"] = to
    mime["Subject"] = subject
    return mime


def send_message(account: dict, to: str, subject: str, body: str) -> bytes:
    """Send a plain-text message; returns the raw MIME bytes that were sent."""
    sender = account["email"]
    password = secrets_store.get_secret(secrets_store.KIND_IMAP_PASSWORD, sender)
    if not password:
        raise SmtpError(f"No stored password for {sender}; re-add the account.")

    host = account["smtp_host"]
    port = int(account["smtp_port"] or 587)
    mime = build_mime(sender, to, subject, body)

    try:
        if port == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        with server:
            server.login(sender, password)
            server.sendmail(sender, [addr.strip() for addr in to.split(",")],
                            mime.as_bytes())
    except (smtplib.SMTPException, OSError) as e:
        raise SmtpError(f"Sending via {host}:{port} failed: {e}") from e
    return mime.as_bytes()

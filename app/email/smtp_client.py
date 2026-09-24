"""SMTP sending for IMAP accounts (SSL or STARTTLS, password from keyring)."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from app.auth import secrets_store

log = logging.getLogger(__name__)


class SmtpError(Exception):
    pass


def split_addresses(raw: str) -> list[str]:
    """Non-empty, stripped addresses from a comma-separated header value."""
    return [addr.strip() for addr in (raw or "").split(",") if addr.strip()]


def build_mime(sender: str, to: str, subject: str, body: str,
               cc: str = "") -> MIMEText:
    """The message as it goes on the wire.

    BCC IS NOT A HEADER HERE, AND THAT IS THE ENTIRE POINT OF BCC. A blind
    copy is blind because the address travels in the SMTP envelope and NOT
    in the message body every recipient can read. Writing it into the MIME
    would hand the full blind-copy list to everyone who received the
    message - precisely the confidentiality failure the field exists to
    prevent. send_message puts it in the envelope instead.
    """
    mime = MIMEText(body, "plain", "utf-8")
    mime["From"] = sender
    mime["To"] = to
    if cc:
        mime["Cc"] = cc
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
    mime = build_mime(sender, to, subject, body, cc=cc)

    # Everyone who should actually receive it, including the blind copies
    # deliberately absent from the headers above.
    envelope = split_addresses(to) + split_addresses(cc) + split_addresses(bcc)
    if not envelope:
        raise SmtpError("No recipients.")

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

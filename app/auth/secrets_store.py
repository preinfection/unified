"""Secure secret storage backed by the operating system keyring.

On Windows this is the Windows Credential Manager. Nothing is ever written
to disk in plaintext by this module: Gmail OAuth tokens and IMAP passwords
both live here, keyed by "<kind>:<email>".
"""

from __future__ import annotations

import logging
from typing import Optional

import keyring
import keyring.errors

log = logging.getLogger(__name__)

SERVICE = "UnifiedMailbox"

KIND_GMAIL_TOKEN = "gmail-token"
KIND_IMAP_PASSWORD = "imap-password"


def _key(kind: str, email: str) -> str:
    return f"{kind}:{email.strip().lower()}"


def set_secret(kind: str, email: str, secret: str) -> None:
    keyring.set_password(SERVICE, _key(kind, email), secret)


def get_secret(kind: str, email: str) -> Optional[str]:
    try:
        return keyring.get_password(SERVICE, _key(kind, email))
    except keyring.errors.KeyringError as e:
        log.error("Keyring read failed for %s: %s", email, e)
        return None


def delete_secret(kind: str, email: str) -> None:
    try:
        keyring.delete_password(SERVICE, _key(kind, email))
    except keyring.errors.PasswordDeleteError:
        pass  # already gone

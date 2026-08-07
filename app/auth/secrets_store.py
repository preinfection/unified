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

from app.config import LEGACY_APP_NAME

log = logging.getLogger(__name__)

SERVICE = "Unified"

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
        log.error("Keyring read failed (%s): %s", kind, e)
        return None


def get_legacy_secret(kind: str, email: str) -> Optional[str]:
    """Read a secret stored under the app's pre-rename service name.

    Used once by migration.py to carry existing sign-ins forward without
    forcing the user to reconnect every account after an app rename.
    """
    try:
        return keyring.get_password(LEGACY_APP_NAME, _key(kind, email))
    except keyring.errors.KeyringError as e:
        log.error("Legacy keyring read failed (%s): %s", kind, e)
        return None


def delete_secret(kind: str, email: str) -> None:
    try:
        keyring.delete_password(SERVICE, _key(kind, email))
    except keyring.errors.PasswordDeleteError:
        pass  # already gone

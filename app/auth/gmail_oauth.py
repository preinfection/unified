"""Gmail OAuth2 flow and credential management.

Users supply their own OAuth client file (a "Desktop app" client downloaded
from Google Cloud Console) via Settings. The interactive consent flow runs
a temporary local web server and opens the system browser. The resulting
token (access + refresh) is stored only in the OS keyring.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from app import config
from app.auth import secrets_store

log = logging.getLogger(__name__)

# gmail.modify covers reading and changing labels/flags; gmail.send allows sending.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailAuthError(Exception):
    pass


def client_secrets_available() -> bool:
    return config.google_client_secrets_path().exists()


def run_oauth_flow() -> Credentials:
    """Run the interactive browser consent flow. Blocking - call off the UI thread."""
    secrets_file = config.google_client_secrets_path()
    if not secrets_file.exists():
        raise GmailAuthError(
            "No Google OAuth client file configured. Open Settings and select "
            "your credentials.json (create a 'Desktop app' OAuth client in "
            "Google Cloud Console with the Gmail API enabled)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)
    # port=0 picks a free port; the flow blocks until the browser redirects back.
    return flow.run_local_server(port=0, open_browser=True)


def save_token(email: str, creds: Credentials) -> None:
    secrets_store.set_secret(
        secrets_store.KIND_GMAIL_TOKEN, email, creds.to_json()
    )


def load_credentials(email: str) -> Optional[Credentials]:
    """Load stored credentials for an account, refreshing them if expired."""
    raw = secrets_store.get_secret(secrets_store.KIND_GMAIL_TOKEN, email)
    if not raw:
        return None
    try:
        creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    except ValueError as e:
        log.error("Stored Gmail token for %s is invalid: %s", email, e)
        return None
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_token(email, creds)
        except Exception as e:  # network or revoked token
            log.error("Token refresh failed for %s: %s", email, e)
            return None
    return creds


def remove_token(email: str) -> None:
    secrets_store.delete_secret(secrets_store.KIND_GMAIL_TOKEN, email)

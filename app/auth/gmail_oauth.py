"""Gmail OAuth2 flow and credential management.

Users supply their own OAuth client file (a "Desktop app" client downloaded
from Google Cloud Console) via Settings. The interactive consent flow opens
the system browser and receives the redirect on a localhost server.

The flow is implemented here (instead of InstalledAppFlow.run_local_server)
so it can be cancelled and timed out: the loopback server is polled in short
intervals and shut down cleanly on cancel/timeout. Tokens are stored only in
the OS keyring.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import webbrowser
import wsgiref.simple_server
import wsgiref.util
from pathlib import Path
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

_SUCCESS_PAGE = (
    "<html><body style='font-family:sans-serif'>"
    "<p>Sign-in complete. You can close this tab and return to Unified.</p>"
    "</body></html>"
)


class GmailAuthError(Exception):
    pass


class OAuthCancelled(Exception):
    """The user cancelled the sign-in."""


class OAuthTimeout(Exception):
    """The sign-in was not completed within the allowed time."""


def client_secrets_available() -> bool:
    return config.google_client_secrets_path().exists()


class _RedirectWSGIApp:
    """Captures the OAuth redirect request URI and shows a success page."""

    def __init__(self) -> None:
        self.last_request_uri: Optional[str] = None

    def __call__(self, environ, start_response):
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        self.last_request_uri = wsgiref.util.request_uri(environ)
        return [_SUCCESS_PAGE.encode("utf-8")]


class _QuietHandler(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, *args) -> None:  # silence per-request stderr noise
        pass


class CancellableOAuthFlow:
    """Interactive Google sign-in that supports cancel() and a hard timeout.

    run() blocks (call it from a worker thread); cancel() may be called from
    any thread and takes effect within the poll interval. The localhost
    callback server is always closed, on every exit path.
    """

    POLL_SECONDS = 0.25

    def __init__(
        self,
        timeout_seconds: int = 120,
        open_browser: bool = True,
        secrets_file: Path | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.open_browser = open_browser
        self.secrets_file = secrets_file or config.google_client_secrets_path()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> Credentials:
        if not self.secrets_file.exists():
            raise GmailAuthError(
                "No Google OAuth client file configured. Open Settings and select "
                "your credentials.json (create a 'Desktop app' OAuth client in "
                "Google Cloud Console with the Gmail API enabled)."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.secrets_file), SCOPES
        )

        wsgi_app = _RedirectWSGIApp()
        server = wsgiref.simple_server.make_server(
            "localhost", 0, wsgi_app, handler_class=_QuietHandler
        )
        try:
            flow.redirect_uri = f"http://localhost:{server.server_port}/"
            auth_url, _ = flow.authorization_url(prompt="consent")
            if self.open_browser:
                webbrowser.open(auth_url, new=1, autoraise=True)

            # Poll for the redirect so cancel and timeout stay responsive.
            server.timeout = self.POLL_SECONDS
            deadline = time.monotonic() + self.timeout_seconds
            while wsgi_app.last_request_uri is None:
                if self._cancel.is_set():
                    raise OAuthCancelled("Sign-in cancelled")
                if time.monotonic() > deadline:
                    raise OAuthTimeout("Google sign-in timed out")
                server.handle_request()
        finally:
            server.server_close()

        # oauthlib insists on an https scheme when checking the response URL;
        # the loopback redirect is http, so rewrite it (as google-auth does).
        auth_response = wsgi_app.last_request_uri.replace("http", "https", 1)
        flow.fetch_token(authorization_response=auth_response)
        return flow.credentials


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
        log.error("Stored Gmail token is invalid: %s", e)
        return None
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_token(email, creds)
        except Exception as e:  # network or revoked token
            log.error("Token refresh failed: %s", e)
            return None
    return creds


def remove_token(email: str) -> None:
    secrets_store.delete_secret(secrets_store.KIND_GMAIL_TOKEN, email)

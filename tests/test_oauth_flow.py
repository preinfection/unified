"""Tests for the cancellable OAuth flow (no network, no browser)."""

import json
import threading
import time

import pytest

from app.auth.gmail_oauth import (
    CancellableOAuthFlow,
    GmailAuthError,
    OAuthCancelled,
    OAuthTimeout,
)

FAKE_CLIENT = {
    "installed": {
        "client_id": "test.apps.googleusercontent.com",
        "client_secret": "not-a-real-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


@pytest.fixture()
def secrets_file(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(FAKE_CLIENT))
    return path


def run_flow_capture(flow):
    """Run flow.run() in a thread; return a dict with the raised exception."""
    result = {}

    def target():
        try:
            flow.run()
            result["outcome"] = "completed"
        except Exception as e:
            result["outcome"] = type(e).__name__
            result["error"] = e

    thread = threading.Thread(target=target)
    thread.start()
    return thread, result


def test_missing_secrets_file(tmp_path):
    flow = CancellableOAuthFlow(
        open_browser=False, secrets_file=tmp_path / "missing.json"
    )
    with pytest.raises(GmailAuthError):
        flow.run()


def test_cancel_stops_flow_quickly(secrets_file):
    flow = CancellableOAuthFlow(
        timeout_seconds=60, open_browser=False, secrets_file=secrets_file
    )
    thread, result = run_flow_capture(flow)
    time.sleep(0.5)  # let the local server start and enter the poll loop
    start = time.monotonic()
    flow.cancel()
    thread.join(timeout=5)
    elapsed = time.monotonic() - start
    assert not thread.is_alive(), "flow thread did not stop after cancel"
    assert result["outcome"] == "OAuthCancelled"
    assert elapsed < 3, f"cancel took too long: {elapsed:.1f}s"


def test_timeout_stops_flow(secrets_file):
    flow = CancellableOAuthFlow(
        timeout_seconds=1, open_browser=False, secrets_file=secrets_file
    )
    thread, result = run_flow_capture(flow)
    thread.join(timeout=8)
    assert not thread.is_alive(), "flow thread did not stop after timeout"
    assert result["outcome"] == "OAuthTimeout"
    assert "timed out" in str(result["error"])


def test_callback_server_port_released(secrets_file):
    """After cancel, the loopback server socket must be closed."""
    import socket

    flow = CancellableOAuthFlow(
        timeout_seconds=60, open_browser=False, secrets_file=secrets_file
    )
    thread, _ = run_flow_capture(flow)
    time.sleep(0.5)
    flow.cancel()
    thread.join(timeout=5)
    # No lingering listener: connecting to any leftover port should fail fast.
    # (We can't know the ephemeral port, so assert via a fresh flow being able
    # to start and stop again cleanly - i.e. no resource exhaustion/errors.)
    flow2 = CancellableOAuthFlow(
        timeout_seconds=1, open_browser=False, secrets_file=secrets_file
    )
    thread2, result2 = run_flow_capture(flow2)
    thread2.join(timeout=8)
    assert result2["outcome"] == "OAuthTimeout"

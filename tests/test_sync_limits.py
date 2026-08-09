"""Tests for the network/cache download bound.

The behavior these lock down: a routine sync must cache only the newest
INITIAL_SYNC_LIMIT messages per folder, NOT mirror the whole mailbox. A
25,000-message account previously cost ~50 Gmail list round trips plus
metadata fetches for all 25,000 messages on first run.

These drive a fake Gmail service that counts API calls, so the assertions
are about real request counts rather than about the shape of the code.
"""
from __future__ import annotations

import pytest

from app.email import gmail_client as gmail_mod
from app.email.gmail_client import GmailClient
from app.services.sync_service import INITIAL_SYNC_LIMIT

TOTAL_SERVER_MESSAGES = 25_000
PAGE_SIZE = 500


class _FakeExecutable:
    def __init__(self, payload, counter, kind):
        self._payload = payload
        self._counter = counter
        self._kind = kind

    def execute(self):
        self._counter[self._kind] += 1
        return self._payload


class _FakeMessages:
    """Stands in for service.users().messages(): serves ids newest-first
    in pages, exactly like the real API, and counts list calls."""

    def __init__(self, counter, total=TOTAL_SERVER_MESSAGES):
        self._counter = counter
        self._total = total

    def list(self, userId, labelIds, maxResults, pageToken=None, q=None):
        start = int(pageToken) if pageToken else 0
        end = min(start + maxResults, self._total)
        payload = {
            "messages": [{"id": f"m{i}"} for i in range(start, end)],
        }
        if end < self._total:
            payload["nextPageToken"] = str(end)
        return _FakeExecutable(payload, self._counter, "list")


class _FakeService:
    def __init__(self, counter, total=TOTAL_SERVER_MESSAGES):
        self._messages = _FakeMessages(counter, total)

    def users(self):
        return self

    def messages(self):
        return self._messages


@pytest.fixture()
def counted_client(monkeypatch):
    counter = {"list": 0}
    monkeypatch.setattr(gmail_mod.gmail_oauth, "load_credentials",
                        lambda email: object())
    monkeypatch.setattr(gmail_mod, "build",
                        lambda *a, **k: _FakeService(counter))
    client = GmailClient("you@example.com")
    return client, counter


def test_capped_listing_does_not_walk_a_25k_mailbox(counted_client):
    client, counter = counted_client
    ids, more_remain = client.list_recent_message_ids("inbox", limit=INITIAL_SYNC_LIMIT)

    assert len(ids) == INITIAL_SYNC_LIMIT
    assert more_remain is True, "must report that older mail remains server-side"
    # 200 ids at <=500 per page is a single round trip - not the ~50 a
    # full 25,000-message walk would cost.
    assert counter["list"] == 1


def test_capped_listing_returns_the_newest_messages(counted_client):
    """Gmail returns ids newest-first, so the capped slice must be the
    head of that ordering - the newest mail, not an arbitrary window."""
    client, _ = counted_client
    ids, _ = client.list_recent_message_ids("inbox", limit=INITIAL_SYNC_LIMIT)
    assert ids[0] == "m0"
    assert ids[-1] == f"m{INITIAL_SYNC_LIMIT - 1}"


def test_uncapped_listing_still_walks_everything_when_asked(counted_client):
    """list_all_message_ids is still available for callers that genuinely
    need the complete server-side set (deletion pruning) - the cap is a
    policy applied by sync, not a capability that was removed."""
    client, counter = counted_client
    ids = client.list_all_message_ids("inbox")
    assert len(ids) == TOTAL_SERVER_MESSAGES
    assert counter["list"] == TOTAL_SERVER_MESSAGES // PAGE_SIZE


def test_small_mailbox_reports_no_more_remaining(monkeypatch):
    """A folder smaller than the cap must report more_remain=False, which
    is what re-enables deletion pruning for that folder."""
    counter = {"list": 0}
    monkeypatch.setattr(gmail_mod.gmail_oauth, "load_credentials",
                        lambda email: object())
    monkeypatch.setattr(gmail_mod, "build",
                        lambda *a, **k: _FakeService(counter, total=42))
    client = GmailClient("you@example.com")

    ids, more_remain = client.list_recent_message_ids("inbox", limit=INITIAL_SYNC_LIMIT)
    assert len(ids) == 42
    assert more_remain is False


def test_initial_sync_limit_is_the_documented_200(counted_client):
    """The cache target the product promises. A change here is a product
    decision, not an implementation detail - this pins it."""
    assert INITIAL_SYNC_LIMIT == 200

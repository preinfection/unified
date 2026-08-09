"""Regression tests for MainWindow's reload/pagination/sync-dedup behavior:

- the initial Unified Mailbox view renders exactly 100 cached rows, not
  the whole table
- "Load more" raises that in fixed increments
- switching categories/accounts is a local, cheap operation that never
  calls into SyncManager (no re-sync triggered by a view change)
- a debounced reload skips re-querying the email list for a single-
  account view when the sync event that triggered it was for a
  *different* account (cached data for the account on screen is never
  unnecessarily re-fetched/re-rendered)

Runs headless (QT_QPA_PLATFORM=offscreen) so it doesn't need a real
display, consistent with how this was verified manually before being
locked in as a test.
"""
from __future__ import annotations

import os
import threading
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

from app import config
from app.database import Database
from app.services import sync_service
from app.ui import main_window as main_window_mod


def _make_stub_older_worker(created: list):
    """Builds a stand-in for OlderFetchWorker that records the fetches a
    test triggered and never actually starts a thread or touches the
    network - so 'did this reach for the network?' is observable."""

    class _StubOlderWorker(QThread):
        loaded = Signal(int, int)
        failed = Signal(int, str)

        def __init__(self, db_path, account, folder="inbox", batch_size=200, parent=None):
            super().__init__(parent)
            created.append({"account": account, "folder": folder})

        def start(self):  # never runs; keeps the "in flight" state open
            pass

        def wait(self, msec=0):
            return True

    return _StubOlderWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _StubWorker(QThread):
    """Same role as the stub in test_sync_manager.py: a stand-in for
    AccountSyncWorker that blocks in run() until stopped, so a test can
    hold a "sync in progress" state open deterministically without doing
    real network I/O."""

    progress = Signal(int, str, int, int)
    result_ready = Signal(int, dict)

    def __init__(self, db_path, account_id, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.account_id = account_id
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        self._stop_event.wait(timeout=5)


@pytest.fixture()
def seeded_db(tmp_path):
    db = Database(tmp_path / "mailbox.db")
    aid1 = db.add_account("you@example.com", "gmail")
    aid2 = db.add_account("work@company.com", "imap", imap_host="x", smtp_host="x")
    batch = []
    for i in range(150):
        for aid in (aid1, aid2):
            batch.append(dict(
                account_id=aid, uid=f"{aid}-{i}", folder="inbox",
                sender_name="Sender", sender_email="s@example.com",
                subject=f"Message {i}", snippet="", body_text="", body_html="",
                date_ts=1_900_000_000 - i, is_read=0, is_starred=0,
                has_attachments=0, body_fetched=1,
            ))
    db.upsert_emails(batch)
    yield db, aid1, aid2
    db.close()


@pytest.fixture()
def window(qapp, seeded_db, monkeypatch, tmp_path):
    monkeypatch.setattr(sync_service, "AccountSyncWorker", _StubWorker)
    db, aid1, aid2 = seeded_db
    # tmp_path, never the real %APPDATA%\Unified - this must not touch the
    # developer's actual settings file.
    settings = config.Settings(tmp_path / "unused-settings.json")
    from app.ui.main_window import MainWindow
    win = MainWindow(db, settings)
    yield win, aid1, aid2
    for worker in list(win.sync._workers.values()):
        worker.request_stop()
        worker.wait(2000)


# --------------------------------------------------------------- pagination

def test_initial_unified_mailbox_shows_100_rows(window):
    win, _, _ = window
    assert win.email_list.row_count() == 100


def test_load_more_raises_the_limit_by_one_page(window):
    win, _, _ = window
    win._load_more()
    assert win.email_list.row_count() == 200


# ----------------------------------------------- search: local, then provider

def _make_stub_search_worker(created: list):
    class _StubSearchWorker(QThread):
        loaded = Signal(int, int)
        failed = Signal(int, str)

        def __init__(self, db_path, account, query, folder="inbox",
                     limit=100, parent=None):
            super().__init__(parent)
            created.append({"account": account, "query": query, "folder": folder})

        def start(self):
            pass

        def wait(self, msec=0):
            return True

    return _StubSearchWorker


def test_short_search_fragments_do_not_hit_the_provider(window, monkeypatch):
    """Mid-typing must stay local - a server-side search per keystroke
    would be abusive and slow."""
    win, _, _ = window
    created = []
    monkeypatch.setattr(main_window_mod, "RemoteSearchWorker",
                        _make_stub_search_worker(created))
    win.toolbar.search_edit.setText("in")
    win._run_search()
    assert not created


def test_deliberate_search_escalates_to_the_provider(window, monkeypatch):
    win, _, _ = window
    created = []
    monkeypatch.setattr(main_window_mod, "RemoteSearchWorker",
                        _make_stub_search_worker(created))
    win.toolbar.search_edit.setText("invoice from amazon")
    win._run_search()
    assert created, "a deliberate search must reach the providers"
    assert {c["query"] for c in created} == {"invoice from amazon"}
    # One per connected account.
    assert len(created) == len(win.db.get_accounts())


def test_repeating_the_same_search_does_not_re_hit_the_provider(window, monkeypatch):
    win, _, _ = window
    created = []
    monkeypatch.setattr(main_window_mod, "RemoteSearchWorker",
                        _make_stub_search_worker(created))
    win.toolbar.search_edit.setText("invoice from amazon")
    win._run_search()
    first = len(created)
    for _ in range(3):
        win._run_search()
    assert len(created) == first


def test_local_results_are_shown_without_waiting_for_the_provider(window, monkeypatch):
    """The visible list must be populated from cache synchronously - the
    remote search only ever adds to it later."""
    win, aid1, _ = window
    monkeypatch.setattr(main_window_mod, "RemoteSearchWorker",
                        _make_stub_search_worker([]))
    win.db.upsert_email(dict(
        account_id=aid1, uid="local-hit", folder="inbox",
        sender_name="Amazon", sender_email="a@amazon.com",
        subject="Your invoice from Amazon", snippet="", body_text="",
        body_html="", date_ts=1_900_500_000, is_read=0, is_starred=0,
        has_attachments=0, body_fetched=1,
    ))
    win.toolbar.search_edit.setText("invoice from amazon")
    win._run_search()
    assert win.email_list.row_count() == 1


# ------------------------------------------- Load More: cache before network

def test_load_more_within_the_cache_makes_no_network_request(window, monkeypatch):
    """300 messages are cached, so paging 100 -> 200 must be served
    entirely from SQLite - no older-message fetch may be started."""
    win, _, _ = window
    created = []
    monkeypatch.setattr(main_window_mod, "OlderFetchWorker",
                        _make_stub_older_worker(created))
    win._load_more()
    assert win.email_list.row_count() == 200
    assert not created, "paging within cached rows must not hit the network"


def test_load_more_past_the_cache_boundary_fetches_older_messages(window, monkeypatch):
    """Once the cached rows run out, and only then, an older-message
    fetch is dispatched per account."""
    win, _, _ = window
    created = []
    monkeypatch.setattr(main_window_mod, "OlderFetchWorker",
                        _make_stub_older_worker(created))

    # 300 cached rows total; page up past all of them.
    for _ in range(4):
        win._load_more()

    assert created, "expected an older-message fetch once the cache ran out"
    # One per account, never more.
    assert len(created) == len({c["account"]["id"] for c in created})


def test_repeated_load_more_does_not_stack_duplicate_older_fetches(window, monkeypatch):
    """Clicking Load More repeatedly while a fetch is in flight must not
    spawn a second fetch for the same account."""
    win, _, _ = window
    created = []
    monkeypatch.setattr(main_window_mod, "OlderFetchWorker",
                        _make_stub_older_worker(created))

    for _ in range(4):
        win._load_more()
    first_round = len(created)
    # More clicks while the (never-finishing) stub fetches are in flight.
    for _ in range(5):
        win._load_more()
    assert len(created) == first_round


# ------------------------------------------------------- category switching

def test_switching_categories_never_calls_request_sync(window):
    win, aid1, _ = window
    win.sync.request_sync = MagicMock(wraps=win.sync.request_sync)

    win._on_view_selected("starred")
    win._on_view_selected("sent")
    win._on_account_selected(aid1)
    win._on_view_selected("inbox")

    win.sync.request_sync.assert_not_called()


def test_returning_to_unified_mailbox_shows_cached_data_immediately(window):
    win, _, _ = window
    assert win.email_list.row_count() == 100
    win._on_view_selected("starred")
    assert win.email_list.row_count() == 0  # no starred messages seeded
    win._on_view_selected("inbox")
    assert win.email_list.row_count() == 100


def test_switching_categories_does_not_touch_sidebar_widgets(window):
    """reload_sidebar() must not rebuild AccountItem widgets on a plain
    view switch - only reload_email_list() should run."""
    win, aid1, _ = window
    items_before = dict(win.sidebar._account_items)
    win._on_view_selected("starred")
    win._on_view_selected("inbox")
    win._on_account_selected(aid1)
    win._on_view_selected("inbox")
    # Same AccountItem instances, not torn down and recreated.
    assert win.sidebar._account_items == items_before
    for aid, item in win.sidebar._account_items.items():
        assert item is items_before[aid]


# --------------------------------------------------- debounced sync reloads

def test_progress_for_a_different_account_skips_reloading_the_current_view(window):
    """A single-account view scoped to account A must not re-query/re-
    render when a progress signal arrives for account B - the cached rows
    already on screen for A are untouched."""
    win, aid1, aid2 = window
    win._on_account_selected(aid1)
    win.email_list.set_rows = MagicMock(wraps=win.email_list.set_rows)

    win._on_account_progress(aid2, "Syncing metadata", 10, 100)
    win._do_scheduled_reload()
    win.email_list.set_rows.assert_not_called()

    win._on_account_progress(aid1, "Syncing metadata", 10, 100)
    win._do_scheduled_reload()
    win.email_list.set_rows.assert_called_once()


def test_progress_always_refreshes_the_unified_mailbox_view(window):
    """The Unified Mailbox view is scoped to no single account, so any
    account's progress is relevant and must still refresh it."""
    win, aid1, aid2 = window
    assert win.current_account_id is None
    win.email_list.set_rows = MagicMock(wraps=win.email_list.set_rows)

    win._on_account_progress(aid2, "Syncing metadata", 10, 100)
    win._do_scheduled_reload()
    win.email_list.set_rows.assert_called_once()


def test_user_action_reload_always_refreshes_regardless_of_current_view(window):
    """_schedule_reload() with no account_id (star/read/delete actions)
    must keep refreshing unconditionally - only sync-progress reloads are
    scoped to the account that actually changed."""
    win, aid1, aid2 = window
    win._on_account_selected(aid2)
    win.email_list.set_rows = MagicMock(wraps=win.email_list.set_rows)

    win._schedule_reload()  # no account_id, e.g. after starring a message
    win._do_scheduled_reload()
    win.email_list.set_rows.assert_called_once()

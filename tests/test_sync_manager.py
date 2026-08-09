"""Tests for SyncManager's dedup/queueing: the single source of truth that
must prevent a UI action (switching views, re-selecting an account, a
second Refresh click) from ever starting a second sync job for an account
that's already syncing.
"""

from __future__ import annotations

import threading

import pytest
from PySide6.QtCore import QCoreApplication, QThread, Signal

from app.database import Database
from app.services import sync_service
from app.services.sync_service import SyncManager


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


class _StubWorker(QThread):
    """Stands in for AccountSyncWorker: same signal surface SyncManager
    depends on, but run() just blocks until told to stop instead of doing
    real network/database work - so a test can deterministically hold a
    "sync in progress" state open and assert against it."""

    progress = Signal(int, str, int, int)
    result_ready = Signal(int, dict)

    def __init__(self, db_path: str, account_id: int, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.account_id = account_id
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        self._stop_event.wait(timeout=5)


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def test_request_sync_does_not_duplicate_a_running_worker(qapp, tmp_path, monkeypatch, db):
    monkeypatch.setattr(sync_service, "AccountSyncWorker", _StubWorker)
    aid = db.add_account("a@example.com", "gmail")
    manager = SyncManager(db.path)

    manager.request_sync([aid])
    assert len(manager._workers) == 1
    first_worker = manager._workers[aid]
    assert isinstance(first_worker, _StubWorker)

    # The kind of call the UI now makes freely: view switches, re-selecting
    # the same account, a stray extra Refresh click - none of it must spawn
    # a second worker for an account still mid-sync.
    for _ in range(5):
        manager.request_sync([aid])
    assert len(manager._workers) == 1
    assert manager._workers[aid] is first_worker
    assert manager._queue == []
    assert manager.is_account_pending(aid)

    first_worker.request_stop()
    first_worker.wait(2000)


def test_request_sync_queues_beyond_max_parallel(qapp, tmp_path, monkeypatch, db):
    monkeypatch.setattr(sync_service, "AccountSyncWorker", _StubWorker)
    ids = [db.add_account(f"a{i}@example.com", "gmail") for i in range(3)]
    manager = SyncManager(db.path)
    assert manager.MAX_PARALLEL == 2

    manager.request_sync(ids)
    assert len(manager._workers) == 2
    assert manager._queue == [ids[2]]
    assert manager.is_account_pending(ids[2])

    # Re-requesting the already-queued (not yet started) account must not
    # add a second queue entry either.
    manager.request_sync([ids[2]])
    assert manager._queue == [ids[2]]

    for worker in list(manager._workers.values()):
        worker.request_stop()
        worker.wait(2000)

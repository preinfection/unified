"""The console: real log records, drawn cheaply, read comfortably.

Guards what the terminal-style redesign must not lose - routing from the
logging system (including from worker threads), levels, filters, text
selection and copy - and what it added: batching under bursts, follow /
pause behaviour, an empty state per filter, and re-theming.
"""
from __future__ import annotations

import logging
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication

from app.ui import console as console_mod
from app.ui import theme as t
from app.ui.console import FLUSH_MS, MAX_RECORDS, ConsoleWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def settle(ms: int = FLUSH_MS * 3) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture()
def console(qapp):
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.DEBUG)
    widget = ConsoleWidget()
    widget.resize(900, 260)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.detach()
    widget.close()
    root.setLevel(old_level)


def lines(widget) -> list[str]:
    return [ln for ln in widget.toPlainText().splitlines() if ln.strip()]


def test_records_from_the_logging_system_appear_in_columns(console):
    logging.getLogger("app.services.sync_service").info("Account 1: connected")
    logging.getLogger("app.database.db").warning("Database check found issues")
    logging.getLogger("app.email.gmail_client").error("HTTP 503")
    out = lines(console)
    assert len(out) == 3
    time_, level, source, *message = out[0].split()
    assert len(time_) == 8 and time_.count(":") == 2
    assert (level, source, " ".join(message)) == ("INFO", "SYNC", "Account 1: connected")
    assert out[1].split()[1:3] == ["WARN", "DB"]
    assert out[2].split()[1:3] == ["ERROR", "API"]
    # The message column starts at the same place on every row.
    starts = {ln.index(m) for ln, m in zip(out, ("Account", "Database", "HTTP"))}
    assert len(starts) == 1, f"messages start at {starts}"


def test_debug_stays_out(console):
    logging.getLogger("app.x").debug("noise")
    assert lines(console) == []


def test_a_worker_thread_can_log_safely(console):
    worker = threading.Thread(
        target=lambda: logging.getLogger("app.services.sync_service").info("from a thread")
    )
    worker.start()
    worker.join()
    settle()
    assert any("from a thread" in ln for ln in lines(console))


def test_a_burst_is_drawn_in_one_pass(console, monkeypatch):
    """A sync logs hundreds of lines a second; drawing each on arrival
    repainted the pane hundreds of times."""
    calls = []
    real = console._flush

    def counting():
        calls.append(len(console._pending))
        real()

    monkeypatch.setattr(console, "_flush", counting)
    console._flush_timer.timeout.disconnect()
    console._flush_timer.timeout.connect(counting)
    log = logging.getLogger("app.services.sync_service")
    for i in range(1500):
        log.info("batch %d", i)
    settle()
    assert calls == [1500], f"flushed {len(calls)} times: {calls[:5]}"
    assert len(lines(console)) == 1500


def test_the_log_is_bounded(console):
    log = logging.getLogger("app.services.sync_service")
    for i in range(MAX_RECORDS + 250):
        log.info("line %d", i)
    settle()
    out = lines(console)
    assert len(out) == MAX_RECORDS
    assert out[-1].endswith(f"line {MAX_RECORDS + 249}")


def test_filters_narrow_and_restore(console):
    logging.getLogger("app.services.sync_service").info("sync line")
    logging.getLogger("app.database.db").info("db line")
    logging.getLogger("app.email.imap_client").warning("imap warning")
    settle()
    console._set_filter("ERRORS")
    assert [ln.split()[1] for ln in lines(console)] == ["WARN"]
    console._set_filter("DATABASE")
    assert all("db line" in ln for ln in lines(console))
    console._set_filter("ALL")
    assert len(lines(console)) == 3


def test_each_filter_has_an_empty_state_of_its_own(console):
    assert console.view.document().isEmpty()
    assert console.view.empty_title == "No activity yet"
    console._set_filter("ERRORS")
    assert console.view.empty_title == "No problems"
    console._set_filter("ALL")


def test_scrolling_up_pauses_and_returning_resumes(console, qapp):
    log = logging.getLogger("app.services.sync_service")
    for i in range(200):
        log.info("line %d", i)
    settle()
    bar = console.view.verticalScrollBar()
    assert console.is_following() and bar.value() == bar.maximum()
    bar.setValue(bar.maximum() // 3)
    assert not console.is_following(), "reading back did not pause"
    assert not console.follow_toggle.isChecked()
    kept = bar.value()
    log.info("arrives while paused")
    settle()
    assert bar.value() == kept, "a new line yanked the reader to the bottom"
    console.follow_toggle.setChecked(True)
    assert bar.value() == bar.maximum()


def test_text_is_selectable_and_copyable(console, qapp):
    flags = console.view.textInteractionFlags()
    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
    assert flags & Qt.TextInteractionFlag.TextSelectableByKeyboard
    logging.getLogger("app.x").info("copy me")
    settle()
    console._copy()
    assert "copy me" in QApplication.clipboard().text()


def test_clear_empties_the_pane_but_keeps_listening(console):
    logging.getLogger("app.x").info("before")
    settle()
    console._clear()
    assert lines(console) == []
    logging.getLogger("app.x").info("after")
    assert lines(console)[-1].endswith("after")


def test_a_theme_switch_recolours_every_line(console):
    logging.getLogger("app.x").warning("careful")
    settle()
    try:
        t.apply_mode("light")
        console.retheme()
        cursor = console.view.document().find("WARN")
        assert cursor.charFormat().foreground().color().name() == t.WARNING.lower()
    finally:
        t.apply_mode("dark")
        console.retheme()


def test_detach_stops_the_routing(qapp):
    widget = ConsoleWidget()
    handler = widget._handler
    assert handler in logging.getLogger().handlers
    widget.detach()
    assert handler not in logging.getLogger().handlers


def test_categories_are_unchanged_for_the_existing_loggers():
    assert console_mod.categorize("app.services.sync_service") == "SYNC"
    assert console_mod.categorize("app.database.db") == "DATABASE"
    assert console_mod.categorize("app.auth.gmail_oauth") == "API"
    assert console_mod.categorize("app.ui.main_window") == "APP"

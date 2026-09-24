"""The dock, the toolbar it sits in, and the location model behind both.

The folders moved from the sidebar to a dock at the top centre. These tests
guard what that move promised:

  * ONE LOCATION, TWO AXES. The folder (dock) and the scope (sidebar) are
    independent, both always shown, and owned by the window alone - never
    by the two widgets separately, which is how the old drawer came to
    show two selections at once.
  * MAGNIFICATION THAT STAYS INSIDE ITS BOX. Cells grow continuously with
    the pointer, but nothing else in the toolbar moves, ever.
  * THE UNREAD COUNT SURVIVED THE MOVE, and follows the scope.
  * THE KEYBOARD STILL WORKS, and the dock's keys are not eaten by the
    window's shortcuts.
  * THE EMPTY STATE IS A LAYOUT, not the populated layout with the data
    taken out.

Geometry is measured, not assumed: "the dock is centred" means its centre
is within a pixel of the window's.
"""
from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QEventLoop, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from app import config
from app.database import Database
from app.services import sync_service
from app.ui import motion, theme as t
from app.ui.components.dock import (
    CELL,
    CELL_PEAK,
    REACH,
    Dock,
    badge_text,
    falloff,
)
from app.ui.components.toolbar import SEARCH_MAX, TopToolBar


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet
    app.setFont(t.make_font("field_value"))
    app.setStyleSheet(get_stylesheet())
    yield app


def settle(ms: int = 320) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture()
def dock(qapp):
    bar = Dock()
    bar.show()
    qapp.processEvents()
    yield bar
    bar.close()
    motion.set_motion_enabled(True)


# ================================================================ the dock

def test_the_dock_holds_the_folders_then_the_actions(dock):
    keys = [item.key for item in dock.items]
    assert keys == ["inbox", "starred", "sent", "trash", "add_account", "settings"]
    assert [i.isCheckable() for i in dock.items] == [True] * 4 + [False] * 2
    # The separator sits between the last folder and the first action.
    last_folder = dock.cell_rect_in_dock(dock.item("trash"))
    first_action = dock.cell_rect_in_dock(dock.item("add_account"))
    assert last_folder.right() < dock.separator_x() < first_action.left()


def test_every_cell_has_a_name_for_a_screen_reader(dock):
    names = [item.accessibleName() for item in dock.items]
    assert names == ["Inbox", "Starred", "Sent", "Trash", "Add account", "Settings"]


def test_the_falloff_is_continuous_and_peaks_on_the_cell():
    assert falloff(0) == 1.0
    assert falloff(REACH) == 0.0 and falloff(-REACH * 2) == 0.0
    samples = [falloff(d) for d in range(0, REACH + 1)]
    assert all(a >= b for a, b in zip(samples, samples[1:])), "not monotonic"
    # No step anywhere: adjacent pixels never differ by more than a sliver.
    assert max(a - b for a, b in zip(samples, samples[1:])) < 0.02


def test_cells_grow_toward_the_pointer_and_nowhere_else(dock):
    motion.set_motion_enabled(True)
    sent = dock.item("sent")
    dock._pointer_at(sent.x() + sent.width() / 2)
    settle(500)
    sizes = {item.key: item.size_now for item in dock.items}
    assert sizes["sent"] == pytest.approx(CELL_PEAK, abs=0.2)
    assert CELL < sizes["starred"] < CELL_PEAK
    assert CELL < sizes["trash"] < CELL_PEAK
    assert sizes["settings"] == pytest.approx(CELL, abs=0.2), "reach is too long"
    assert not dock.is_settling(), "the frame timer outlived the motion"


def test_it_settles_back_when_the_pointer_leaves(dock):
    motion.set_motion_enabled(True)
    dock._pointer_at(dock.item("starred").x() + 10)
    settle(400)
    dock.leaveEvent(QEvent(QEvent.Type.Leave))
    settle(500)
    assert all(item.size_now == pytest.approx(CELL, abs=0.05) for item in dock.items)
    assert not dock.is_settling()


def test_the_spring_never_overshoots(dock):
    """Overdamped by construction: a dock that wobbles past its target is
    a toy. Sampled every frame on the way up."""
    motion.set_motion_enabled(True)
    item = dock.item("trash")
    dock._pointer_at(item.x() + item.width() / 2)
    peak = 0.0
    for _ in range(40):
        settle(12)
        peak = max(peak, item.size_now)
    assert peak <= CELL_PEAK + 0.05, f"overshot to {peak:.2f}"


def test_magnification_never_leaves_the_reserved_box(dock):
    """The widget reserves the most width magnification can use, so the
    pill can grow without anything outside the dock moving."""
    motion.set_motion_enabled(True)
    width_before = dock.width()
    for x in range(0, dock.width(), 7):
        for item in dock.items:
            item.size_now = item.size_target = CELL
        dock._pointer_at(float(x))
        for item in dock.items:      # jump straight to the targets
            item.size_now = item.size_target
        dock._layout_cells()
        pill = dock.pill_rect()
        assert pill.left() >= -0.01 and pill.right() <= dock.width() + 0.01, (
            f"pointer at {x}: pill {pill} escapes {dock.width()}"
        )
    assert dock.width() == width_before


def test_no_magnification_and_no_timer_under_reduced_motion(dock):
    motion.set_motion_enabled(False)
    dock._pointer_at(dock.item("sent").x() + 12)
    assert all(item.size_now == CELL for item in dock.items)
    assert not dock.is_settling()


# ------------------------------------------------------------------- unread

def test_the_badge_counts_and_caps(dock):
    assert dock.badge_rect().isNull(), "a badge with nothing unread"
    dock.set_unread(7)
    assert not dock.badge_rect().isNull()
    assert dock.item("inbox").accessibleName() == "Inbox, 7 unread"
    assert badge_text(7) == "7" and badge_text(99) == "99" and badge_text(4213) == "99+"
    dock.set_unread(0)
    assert dock.badge_rect().isNull()
    assert dock.item("inbox").accessibleName() == "Inbox"


def test_the_badge_never_moves_the_dock(dock):
    """The count is an overlay: showing, growing or clearing it must not
    shift a single cell."""
    before = [item.geometry() for item in dock.items]
    for count in (3, 42, 4213, 0):
        dock.set_unread(count)
        assert [item.geometry() for item in dock.items] == before
        badge = dock.badge_rect()
        if not badge.isNull():
            assert dock.rect().toRectF().contains(badge), "the badge is clipped"


# ----------------------------------------------------------------- keyboard

def test_arrow_keys_walk_the_dock(dock, qapp):
    dock.activateWindow()
    dock.item("inbox").setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    QApplication.sendEvent(
        dock.item("inbox"),
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier),
    )
    assert dock.item("starred").hasFocus()
    QApplication.sendEvent(
        dock.item("starred"),
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_End, Qt.KeyboardModifier.NoModifier),
    )
    assert dock.item("settings").hasFocus()


def test_enter_on_a_focused_folder_asks_for_that_folder(dock):
    seen = []
    dock.folder_requested.connect(seen.append)
    QApplication.sendEvent(
        dock.item("sent"),
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
    )
    assert seen == ["sent"]


def test_the_dock_claims_its_keys_from_the_window_shortcuts(dock):
    """Enter is bound window-wide to "open the focused message". A focused
    dock cell accepts the shortcut override, so Enter means the cell."""
    for key in (Qt.Key.Key_Return, Qt.Key.Key_Left, Qt.Key.Key_Right):
        event = QKeyEvent(QEvent.Type.ShortcutOverride, key,
                          Qt.KeyboardModifier.NoModifier)
        event.ignore()
        QApplication.sendEvent(dock.item("sent"), event)
        assert event.isAccepted(), f"{key} would be taken by a window shortcut"
    # ...but not the list's own keys: Down still steps through messages.
    event = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Down,
                      Qt.KeyboardModifier.NoModifier)
    event.ignore()
    QApplication.sendEvent(dock.item("sent"), event)
    assert not event.isAccepted()


def test_a_click_does_not_take_focus_from_the_list(dock):
    """Tab reaches the dock; a click does not pull focus out of the message
    list, or the keyboard would stop working wherever the user was."""
    assert all(item.focusPolicy() == Qt.FocusPolicy.TabFocus for item in dock.items)


def test_a_label_names_the_hovered_cell(dock, qapp):
    dock.show_label_for(dock.item("trash"), immediate=True)
    assert dock.label_text() == "Trash"
    dock.set_unread(4)
    dock.show_label_for(dock.item("inbox"), immediate=True)
    assert "4 unread" in dock.label_text()
    # Once one label is up, the next item is named at once.
    dock.show_label_for(dock.item("sent"))
    assert dock.label_text() == "Sent"


# ================================================================ toolbar

@pytest.fixture()
def band(qapp):
    bar = TopToolBar()
    bar.resize(1440, t.TOOLBAR_HEIGHT)
    bar.show()
    qapp.processEvents()
    yield bar
    bar.close()


def _rects(bar):
    right = [w for w in (*bar._trailing, bar.refresh_btn, bar.console_btn)
             if not w.isHidden()]
    return [bar.compose_btn.geometry(), bar.search_edit.geometry(),
            bar.dock.geometry(), *[w.geometry() for w in right]]


@pytest.mark.parametrize("width", [1920, 1440, 1000, 820])
def test_the_dock_is_centred_and_nothing_overlaps(band, qapp, width):
    band.resize(width, t.TOOLBAR_HEIGHT)
    qapp.processEvents()
    rects = _rects(band)
    for i, a in enumerate(rects):
        assert a.left() >= 0 and a.right() < width, f"{a} leaves the band at {width}"
        for b in rects[i + 1:]:
            assert not a.intersects(b), f"{a} overlaps {b} at {width}px"
    if width >= 1000:
        centre = band.dock.geometry().center().x()
        assert abs(centre - width / 2) <= 1, f"dock centre {centre} at {width}"


def test_the_band_never_narrows_past_its_contents(band, qapp):
    minimum = band.minimumSizeHint().width()
    band.resize(minimum, t.TOOLBAR_HEIGHT)
    qapp.processEvents()
    rects = _rects(band)
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not a.intersects(b), f"{a} overlaps {b} at the minimum"
    assert band.compose_btn.text() == "", "Compose kept its label with no room"
    assert band.compose_btn.toolTip() == "Compose"


def test_the_search_field_is_sized_to_a_query_not_the_window(band, qapp):
    """It used to expand through the whole bar - 1,100px of empty field on
    a first run - and was the most prominent object in the window."""
    band.resize(1920, t.TOOLBAR_HEIGHT)
    qapp.processEvents()
    assert band.search_edit.width() <= SEARCH_MAX


def test_magnifying_the_dock_moves_nothing_else(band, qapp):
    motion.set_motion_enabled(True)
    before = _rects(band)
    dock = band.dock
    dock._pointer_at(dock.item("starred").x() + 10)
    settle(400)
    assert _rects(band) == before
    dock.leaveEvent(QEvent(QEvent.Type.Leave))


# ======================================================== the location model

class _StubWorker(QThread):
    progress = Signal(int, str, int, int)
    result_ready = Signal(int, dict)

    def __init__(self, db_path, account_id, parent=None):
        super().__init__(parent)
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        self._stop.wait(timeout=5)


def _mail(account_id, n, folder="inbox", unread_every=2, prefix="m"):
    return [
        dict(account_id=account_id, uid=f"{prefix}{folder}{i}", folder=folder,
             sender_name="Sender", sender_email="s@example.com",
             subject=f"Message {i}", snippet="snippet", body_text="body",
             body_html="", date_ts=1_900_000_000 - i,
             is_read=0 if i % unread_every == 0 else 1, is_starred=0,
             has_attachments=0, body_fetched=1)
        for i in range(n)
    ]


@pytest.fixture()
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, "AccountSyncWorker", _StubWorker)
    db = Database(tmp_path / "mailbox.db")
    a1 = db.add_account("ada@example.org", "gmail")
    a2 = db.add_account("work@example.com", "imap", imap_host="i", smtp_host="s")
    db.upsert_emails(_mail(a1, 6, prefix="a"))              # 3 unread
    db.upsert_emails(_mail(a2, 4, prefix="b"))              # 2 unread
    db.upsert_emails(_mail(a2, 2, folder="sent", prefix="b"))
    settings = config.Settings(tmp_path / "settings.json")
    from app.ui.main_window import MainWindow
    win = MainWindow(db, settings)
    win.resize(1440, 900)
    win.show()
    qapp.processEvents()
    yield win, db, a1, a2
    for worker in list(win.sync._workers.values()):
        worker.request_stop()
        worker.wait(2000)
    win.close()
    win.deleteLater()
    motion.set_motion_enabled(True)


def _where(win):
    checked = [i.key for i in win.dock.items if i.isChecked()]
    selected = [r.account_id for r in win.sidebar.selected_rows()]
    return checked, selected


def test_folder_and_account_are_both_shown_at_once(window):
    win, db, a1, a2 = window
    win._on_view_selected("sent")
    win._on_account_selected(a2)
    assert (win.current_view, win.current_account_id) == ("sent", a2)
    assert _where(win) == (["sent"], [a2])
    # The list really is that account's Sent, not a stale view.
    assert win.email_list.row_count() == 2
    win._on_view_selected("inbox")
    assert _where(win) == (["inbox"], [a2]), "choosing a folder dropped the account"


def test_exactly_one_folder_and_one_scope_through_any_sequence(window):
    """The bug class this exists for: two widgets each keeping their own
    selection, and a sequence of clicks leaving both - or neither - lit."""
    win, db, a1, a2 = window
    steps = [("view", "trash"), ("scope", a1), ("view", "starred"),
             ("scope", None), ("scope", a2), ("view", "inbox"),
             ("view", "inbox"), ("scope", a2), ("scope", None)]
    for kind, value in steps:
        if kind == "view":
            win.dock.item(value).click()
        else:
            win.sidebar.scope_selected.emit(value)
        checked, selected = _where(win)
        assert checked == [win.current_view], (kind, value, checked)
        assert selected == [win.current_account_id], (kind, value, selected)


def test_the_inbox_badge_counts_the_inbox_it_would_open(window):
    win, db, a1, a2 = window
    assert win.dock.unread() == 3 + 2
    win._on_account_selected(a2)
    assert win.dock.unread() == 2
    win._on_scope_selected(None)
    assert win.dock.unread() == 5


def test_the_badge_follows_reading(window, qapp):
    win, db, a1, a2 = window
    first = next(r for r in win.email_list._model._rows
                 if not r.get("is_header") and not r["is_read"])
    win._on_email_selected(first["id"])
    win._do_scheduled_reload()
    assert win.dock.unread() == 4


def test_folder_shortcuts_follow_the_dock_order(window):
    win, db, a1, a2 = window
    handlers = win._shortcuts.handlers
    for action, folder in (("go_starred", "starred"), ("go_sent", "sent"),
                           ("go_trash", "trash"), ("go_inbox", "inbox")):
        handlers[action]()
        assert win.current_view == folder
        assert win.dock.current_folder() == folder


def test_the_dock_actions_open_their_surfaces(window, monkeypatch):
    win, db, a1, a2 = window
    calls = []
    monkeypatch.setattr(win, "open_add_account", lambda: calls.append("add"))
    monkeypatch.setattr(win, "open_settings", lambda: calls.append("settings"))
    win.dock.item("add_account").click()
    win.dock.item("settings").click()
    assert calls == ["add", "settings"]
    assert win.current_view == "inbox", "an action changed the location"


def test_moving_somewhere_reveals_and_staying_put_does_not(window, monkeypatch):
    win, db, a1, a2 = window
    reveals = []
    monkeypatch.setattr(motion, "reveal", lambda widget, **k: reveals.append(widget))
    win._on_view_selected("sent")
    win._on_view_selected("sent")        # already there
    win.reload_email_list()              # a sync tick
    assert len(reveals) == 1


def test_leaving_a_folder_lets_go_of_its_open_message(window):
    """The reading pane used to keep showing an Inbox message after the
    user moved to Trash - Reply and Delete still aimed at it."""
    win, db, a1, a2 = window
    first = next(r for r in win.email_list._model._rows if not r.get("is_header"))
    win._on_email_selected(first["id"])
    assert win.preview.is_showing_message()
    win._on_view_selected("trash")
    assert win.current_email_id is None
    assert not win.preview.is_showing_message()
    win._on_view_selected("inbox")
    assert not win.preview.is_showing_message()
    assert win.preview._empty._title.text() == "Select a message"


def test_removing_the_account_in_scope_falls_back_to_everyone(window):
    win, db, a1, a2 = window
    win._on_account_selected(a2)
    db.remove_account(a2)
    win.reload_sidebar()
    assert win.current_account_id is None
    assert _where(win)[1] == [None]


def test_the_search_field_says_what_it_will_search(window):
    win, db, a1, a2 = window
    win._on_view_selected("sent")
    assert win.toolbar.search_edit.placeholderText() == "Search sent in all accounts"
    win._on_account_selected(a1)
    assert "ada@example.org" in win.toolbar.search_edit.placeholderText()


# ============================================================ the empty state

@pytest.fixture()
def empty_window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, "AccountSyncWorker", _StubWorker)
    db = Database(tmp_path / "mailbox.db")
    settings = config.Settings(tmp_path / "settings.json")
    from app.ui.main_window import MainWindow
    win = MainWindow(db, settings)
    win.resize(1440, 900)
    win.show()
    qapp.processEvents()
    yield win, db
    win.close()
    win.deleteLater()


def test_no_accounts_is_a_layout_of_its_own(empty_window, qapp):
    """THE EMPTY STATE WAS THE POPULATED LAYOUT WITH THE DATA REMOVED: a
    blank reading pane with a divider down it, and a search field across
    most of the window, around an offer to add an account."""
    win, db = empty_window
    assert win.preview.isHidden(), "a reading pane with nothing to read"
    assert win.center_stack.currentWidget() is win.empty_state
    assert win.empty_state._action.isVisible()
    # The offer is centred in the space the reading pane was holding.
    offer = win.empty_state._action
    centre = offer.mapTo(win, offer.rect().center()).x()
    content_left = win.sidebar.width()
    content_centre = content_left + (win.width() - content_left) / 2
    assert abs(centre - content_centre) <= 2
    toolbar = win.toolbar
    assert not toolbar.search_edit.isEnabled()
    assert not toolbar.refresh_btn.isEnabled()
    assert not toolbar.compose_btn.isEnabled()
    assert toolbar.search_edit.placeholderText() == "Search"
    assert win.statusBar().currentMessage() == "No accounts connected"


def test_the_reading_pane_returns_with_the_first_account(empty_window, qapp):
    win, db = empty_window
    aid = db.add_account("first@example.org", "gmail")
    db.upsert_emails(_mail(aid, 3))
    win.reload_sidebar()
    win.reload_email_list()
    qapp.processEvents()
    assert not win.preview.isHidden()
    assert win.toolbar.search_edit.isEnabled()
    assert win.toolbar.compose_btn.isEnabled()


def test_the_rail_gives_its_width_back_to_the_panes(window, qapp):
    """Collapsing the drawer was meant to give 192px to the list and the
    reading pane. With the drawer inside the splitter the section kept its
    old width and the space went to a dead strip beside the rail."""
    win, db, a1, a2 = window
    motion.set_motion_enabled(False)
    list_left = win.center_stack.mapTo(win, win.center_stack.rect().topLeft()).x()
    win.sidebar.set_collapsed(True, animate=False)
    qapp.processEvents()
    qapp.processEvents()
    collapsed_left = win.center_stack.mapTo(win, win.center_stack.rect().topLeft()).x()
    assert collapsed_left <= win.sidebar.width() + 1, (
        f"the list starts at {collapsed_left}, the rail ends at {win.sidebar.width()}"
    )
    assert collapsed_left < list_left

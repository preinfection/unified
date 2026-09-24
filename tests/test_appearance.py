"""Appearance: theme switching, row density, and the keyboard.

WHY THIS FILE EXISTS. All three of these were built, documented and
unreachable. app/ui/shortcuts.py was imported by nothing, so the app had no
keyboard interface at all. theme.apply_mode() was called exactly once, at
import, with "dark" hardcoded, so the light ramp - generated in OKLCH and
contrast-checked against every surface - could not be displayed. And
EmailListView.set_compact() had no caller, so the compact row height was a
token nothing could select.

Each test below therefore guards a WIRE rather than a value: not "is the
light palette correct" (test_design_system.py covers that) but "can the
application actually get into it, and does the whole window follow".
"""
from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

from app import config
from app.database import Database
from app.services import sync_service
from app.ui import motion, shortcuts
from app.ui import theme as t


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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


@pytest.fixture()
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, "AccountSyncWorker", _StubWorker)
    db = Database(tmp_path / "mailbox.db")
    aid = db.add_account("you@example.com", "gmail")
    db.upsert_emails([
        dict(account_id=aid, uid=f"u{i}", folder="inbox",
             sender_name="Sender", sender_email="s@example.com",
             subject=f"Message {i}", snippet="snippet", body_text="body",
             body_html="", date_ts=1_900_000_000 - i, is_read=0, is_starred=0,
             has_attachments=0, body_fetched=1)
        for i in range(10)
    ])
    settings = config.Settings(tmp_path / "settings.json")
    from app.ui.main_window import MainWindow
    win = MainWindow(db, settings)
    yield win, settings, db
    for worker in list(win.sync._workers.values()):
        worker.request_stop()
        worker.wait(2000)
    # Closed and released, not just left behind: every window a test leaves
    # open is re-polished by every later setStyleSheet and grabbed by every
    # later theme reveal, which made the suite slower with each test.
    win.close()
    win.deleteLater()
    # Leave the module-level palette AND the application stylesheet as the
    # rest of the suite expects them. Restoring only the palette leaves the
    # QApplication holding whichever QSS string the last test built, which
    # is exactly the half-switched state set_theme_mode exists to avoid -
    # and it makes the next test read a stale stylesheet.
    from app.ui.style import get_stylesheet, invalidate_style_cache
    t.apply_mode("dark")
    invalidate_style_cache()
    qapp.setStyleSheet(get_stylesheet())
    motion.set_motion_enabled(True)


# ------------------------------------------------------------------- theme

def test_the_light_palette_is_reachable_at_all(window):
    """The regression this file exists for. apply_mode() had one caller -
    the bottom of theme.py - so no sequence of user actions could reach
    the light ramp."""
    win, _, _ = window
    assert t.MODE == "dark"
    win.set_theme_mode("light")
    assert t.MODE == "light"
    assert t.is_dark() is False


def test_switching_theme_rebinds_the_surfaces_not_just_the_flag(window):
    win, _, _ = window
    dark_floor = t.BG_APP
    win.set_theme_mode("light")
    assert t.BG_APP != dark_floor
    # Light mode must actually be lighter, not merely different.
    from PySide6.QtGui import QColor
    assert QColor(t.BG_APP).lightness() > QColor(dark_floor).lightness()


def test_switching_theme_rebuilds_the_stylesheet(qapp, window):
    """A theme change that only rebinds the module globals leaves every
    QSS-styled widget in the previous palette, because a stylesheet is a
    string Qt already parsed."""
    win, _, _ = window
    before = qapp.styleSheet()
    win.set_theme_mode("light")
    after = qapp.styleSheet()
    assert after != before
    assert t.BG_APP in after


def test_theme_choice_is_remembered(window):
    win, settings, _ = window
    win.set_theme_mode("light")
    assert settings.get("theme_mode") == "light"


def test_toggle_theme_goes_both_ways(window):
    win, _, _ = window
    win.toggle_theme()
    assert t.MODE == "light"
    win.toggle_theme()
    assert t.MODE == "dark"


def test_an_unknown_theme_name_is_refused_rather_than_crashing(window):
    win, _, _ = window
    win.set_theme_mode("solarized")
    assert t.MODE == "dark"


# ----------------------------------------------------------------- density

def test_density_is_reachable_and_changes_the_row_height(window):
    win, settings, _ = window
    delegate = win.email_list._delegate
    comfortable = delegate.row_height()
    win.toggle_density()
    assert delegate.row_height() < comfortable
    assert settings.get("compact_rows") is True
    win.toggle_density()
    assert delegate.row_height() == comfortable


def test_saved_density_is_applied_at_startup(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, "AccountSyncWorker", _StubWorker)
    settings = config.Settings(tmp_path / "settings.json")
    settings.set("compact_rows", True)
    db = Database(tmp_path / "mailbox.db")
    from app.ui.main_window import MainWindow
    win = MainWindow(db, settings)
    try:
        assert win.email_list._delegate.row_height() == t.ROW_HEIGHT_COMPACT
    finally:
        win.close()


# --------------------------------------------------------------- shortcuts

def test_every_binding_has_a_handler(window):
    """A binding with no handler is silently skipped by install(), so it
    appears in the help sheet and does nothing when pressed."""
    win, _, _ = window
    missing = [
        b.action for b in shortcuts.BINDINGS
        if b.action not in win._shortcuts.handlers
    ]
    assert not missing, f"bindings with no handler: {missing}"


def test_shortcuts_are_actually_installed_on_the_window(window):
    win, _, _ = window
    from PySide6.QtGui import QShortcut
    installed = {
        s.key().toString() for s in win.findChildren(QShortcut)
    }
    # A representative spread rather than all of them: this is checking
    # that install() ran, not re-asserting the binding table.
    for key in ("Ctrl+F", "Ctrl+N", "Ctrl+,"):
        assert key in installed, f"{key} was never installed"


def test_j_and_k_step_through_the_list(window):
    win, _, _ = window
    win._step_message(1)
    first = win.email_list.selected_email_id()
    assert first is not None
    win._step_message(1)
    assert win.email_list.selected_email_id() != first
    win._step_message(-1)
    assert win.email_list.selected_email_id() == first


def test_stepping_never_lands_on_a_date_header(window):
    """Date groups are rows in the same flat model and are not selectable;
    stepping onto one would read as the keyboard having stopped."""
    win, _, _ = window
    for _ in range(len(win.email_list._model._rows) + 4):
        win._step_message(1)
        index = win.email_list.currentIndex()
        if index.isValid():
            row = win.email_list._model._rows[index.row()]
            assert not row.get("is_header")


def test_the_help_sheet_lists_every_binding(qapp):
    """Generated from the same table, so it cannot document a keyboard the
    app does not have."""
    from PySide6.QtWidgets import QLabel
    from app.ui.shortcuts_dialog import ShortcutsDialog

    dialog = ShortcutsDialog()
    listed = {label.text() for label in dialog.findChildren(QLabel)}
    for binding in shortcuts.BINDINGS:
        assert binding.label in listed, f"{binding.label} is not in the sheet"


# ------------------------------------------------------------------ motion

def test_reduced_motion_still_reaches_the_end_state(qapp):
    """The bug that makes most reduced-motion implementations worse than
    none: skipping the animation AND the state change it was carrying."""
    from PySide6.QtWidgets import QLabel

    label = QLabel("x")
    label.setVisible(False)
    motion.set_motion_enabled(False)
    try:
        motion.fade_in(label)
        assert label.isVisible()
        effect = label.graphicsEffect()
        assert effect is not None and effect.opacity() == 1.0

        swapped = []
        motion.cross_fade(label, lambda: swapped.append(True))
        assert swapped, "cross_fade skipped the swap instead of the animation"
    finally:
        motion.set_motion_enabled(True)


def test_one_opacity_effect_per_widget_however_many_fades(qapp):
    """A fresh QGraphicsOpacityEffect per call attaches another QObject to
    the widget every time it fades."""
    from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel

    label = QLabel("x")
    for _ in range(5):
        motion.fade_in(label)
    effects = label.findChildren(QGraphicsOpacityEffect)
    assert len(effects) <= 1


# ------------------------------------------------------------- responsive

def _shown(win, qapp):
    """resizeEvent only fires on a widget that has been shown - Qt defers
    it otherwise, so a hidden window silently never runs the responsive
    pass."""
    win.show()
    qapp.processEvents()
    return win


def test_a_narrow_window_collapses_the_sidebar_by_itself(window, qapp):
    """This is a three-pane app, so the drawer's fixed 248px comes
    straight out of the list and the reading pane. At 1000px that is a
    quarter of the window spent on four folder names the user already
    knows."""
    win, _, _ = window
    _shown(win, qapp)
    win.resize(1400, 800)
    qapp.processEvents()
    assert not win.sidebar.is_collapsed()

    win.resize(900, 800)
    qapp.processEvents()
    assert win.sidebar.is_collapsed()


def test_widening_again_brings_it_back(window, qapp):
    win, _, _ = window
    _shown(win, qapp)
    win.resize(900, 800)
    qapp.processEvents()
    win.resize(1400, 800)
    qapp.processEvents()
    assert not win.sidebar.is_collapsed()


def test_an_automatic_collapse_is_not_saved_as_a_preference(window, qapp):
    """Dragging the window small once must not leave the drawer collapsed
    forever afterwards, on every monitor."""
    win, settings, _ = window
    _shown(win, qapp)
    win.resize(900, 800)
    qapp.processEvents()
    assert win.sidebar.is_collapsed()
    assert settings.get("sidebar_collapsed") is False


def test_the_users_own_choice_survives_being_widened(window, qapp):
    """A collapse the user asked for is a preference, and the window does
    not get to overrule it on the next resize."""
    win, settings, _ = window
    _shown(win, qapp)
    win.resize(1400, 800)
    qapp.processEvents()
    win.toggle_sidebar()                 # explicit
    assert win.sidebar.is_collapsed()
    assert settings.get("sidebar_collapsed") is True

    win.resize(1500, 800)                # plenty of room now
    qapp.processEvents()
    assert win.sidebar.is_collapsed(), "the window overruled the user"


# ------------------------------------------------------- keyboard safety

def test_single_letter_shortcuts_stand_down_while_typing(window, qapp):
    """THE CLASSIC WAY SINGLE-KEY SHORTCUTS GET ADDED AND THEN REVERTED.
    `j` must move down the list and must also type the letter j into the
    search box; without the guard this file's whole binding table makes
    the app impossible to type in."""
    win, _, _ = window
    win.show()
    qapp.processEvents()

    win.toolbar.search_edit.setFocus()
    qapp.processEvents()
    assert shortcuts._typing(win), "focus in the search field was not detected"

    # Every literal binding must be suppressed there, and every explicit
    # chord must still work.
    literal = [b for b in shortcuts.BINDINGS if b.literal]
    assert literal, "no single-key bindings left to guard"
    for binding in literal:
        fired = []
        guard = win._shortcuts._guard(binding, lambda: fired.append(True))
        guard()
        assert not fired, f"{binding.keys} fired while typing"

    for binding in (b for b in shortcuts.BINDINGS if not b.literal):
        fired = []
        win._shortcuts._guard(binding, lambda: fired.append(True))()
        assert fired, f"{binding.keys} was suppressed but is not a literal key"


def test_the_guard_releases_once_focus_leaves_the_field(window, qapp):
    win, _, _ = window
    win.show()
    win.toolbar.search_edit.setFocus()
    qapp.processEvents()
    assert shortcuts._typing(win)

    win.email_list.setFocus()
    qapp.processEvents()
    assert not shortcuts._typing(win), "the list is not a text field"


def test_compose_body_also_suppresses_single_letter_shortcuts(window, qapp):
    """A QPlainTextEdit is where people type the most, so it matters most."""
    from app.ui.compose_dialog import ComposeDialog

    win, _, db = window
    dialog = ComposeDialog(db.get_accounts(), win)
    dialog.show()
    dialog.body_edit.setFocus()
    qapp.processEvents()
    assert shortcuts._typing(dialog)
    dialog.close()


def test_escape_backs_out_one_step_at_a_time(window, qapp):
    """Escape clears a search you are in; otherwise it returns to the
    list. It must not do both at once."""
    win, _, _ = window
    win.show()
    win.toolbar.search_edit.setText("engine")
    win.toolbar.search_edit.setFocus()
    qapp.processEvents()

    win._on_escape()
    assert win.toolbar.search_text() == "", "the first Escape did not clear"

    win._on_escape()
    qapp.processEvents()
    assert win.email_list.hasFocus(), "the second Escape did not return focus"

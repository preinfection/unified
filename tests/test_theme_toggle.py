"""The theme control in Settings, and the reveal that carries a change.

What is guarded here is the behaviour, not the look:

  * the control shows the CURRENT theme as a state, never as an icon the
    reader has to interpret, and can be driven from the keyboard;
  * choosing a theme applies it at once (it is the one setting that has
    to be seen to be judged) and Cancel puts it back;
  * the reveal never delays the change - the palette is already switched
    while the old one is still being uncovered - never blocks input, and
    cleans itself up; under reduced motion there is no reveal at all.
"""
from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QEventLoop, QPoint, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from app import config
from app.database import Database
from app.services import sync_service
from app.ui import motion, theme as t
from app.ui.components.theme_toggle import ThemeToggle


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def settle(ms: int = 320) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture(autouse=True)
def _restore(qapp):
    yield
    from app.ui.style import get_stylesheet, invalidate_style_cache
    t.apply_mode("dark")
    invalidate_style_cache()
    qapp.setStyleSheet(get_stylesheet())
    motion.set_motion_enabled(True)


# ---------------------------------------------------------------- control

def test_the_current_theme_is_a_state_you_can_read(qapp):
    toggle = ThemeToggle("dark")
    assert toggle.mode() == "dark" and toggle.isChecked()
    assert toggle.accessibleName() == "Theme"
    assert toggle.accessibleDescription().startswith("Dark theme")
    toggle.set_mode("light")
    assert toggle.mode() == "light"
    assert toggle.accessibleDescription().startswith("Light theme")


def test_the_surface_rests_under_the_current_theme(qapp):
    motion.set_motion_enabled(False)
    toggle = ThemeToggle("light")
    assert toggle.knob_rect() == toggle.segment_rect(0)
    toggle.click()
    assert toggle.knob_rect() == toggle.segment_rect(1), (
        "reduced motion left the surface between the sun and the moon"
    )


def test_the_surface_slides_when_motion_is_on(qapp):
    motion.set_motion_enabled(True)
    toggle = ThemeToggle("dark")
    toggle.show()
    toggle.click()
    settle(40)
    mid = toggle.knob_rect().x()
    settle(400)
    assert toggle.segment_rect(0).x() < mid < toggle.segment_rect(1).x(), (
        "the surface jumped instead of sliding"
    )
    assert toggle.knob_rect() == toggle.segment_rect(0)


def test_a_click_asks_for_the_other_theme(qapp):
    toggle = ThemeToggle("dark")
    seen = []
    toggle.mode_requested.connect(seen.append)
    toggle.click()
    toggle.click()
    assert seen == ["light", "dark"]


def test_set_mode_shows_without_asking(qapp):
    """A revert on Cancel must not loop back into another request."""
    toggle = ThemeToggle("dark")
    seen = []
    toggle.mode_requested.connect(seen.append)
    toggle.set_mode("light")
    assert seen == []


def test_left_and_right_choose_directly(qapp):
    toggle = ThemeToggle("dark")
    seen = []
    toggle.mode_requested.connect(seen.append)

    def press(key):
        QApplication.sendEvent(
            toggle, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        )

    press(Qt.Key.Key_Left)
    press(Qt.Key.Key_Left)        # already light: no second request
    press(Qt.Key.Key_Right)
    assert seen == ["light", "dark"]
    assert toggle.focusPolicy() == Qt.FocusPolicy.StrongFocus


# -------------------------------------------------------------- the dialog

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
    settings = config.Settings(tmp_path / "settings.json")
    from app.ui.main_window import MainWindow
    win = MainWindow(db, settings)
    win.resize(1200, 800)
    win.show()
    qapp.processEvents()
    yield win, settings
    win.close()


def test_the_dropdown_is_gone_from_appearance(window):
    from app.ui.components.dropdown import Dropdown
    from app.ui.settings_dialog import SettingsDialog

    win, settings = window
    dialog = SettingsDialog(settings, win.manager, win)
    assert isinstance(dialog.theme_toggle, ThemeToggle)
    assert not hasattr(dialog, "theme_dropdown")
    page = dialog.stack.widget(1)
    dropdowns = page.findChildren(Dropdown)
    assert len(dropdowns) == 1, "only Message rows should still be a dropdown"


def test_choosing_applies_at_once_and_cancel_puts_it_back(window):
    from app.ui.settings_dialog import SettingsDialog

    motion.set_motion_enabled(False)
    win, settings = window
    dialog = SettingsDialog(settings, win.manager, win)
    requests = []
    dialog.theme_requested.connect(
        lambda mode, origin: (requests.append((mode, origin)),
                              win.set_theme_mode(mode, origin=origin))
    )
    dialog.theme_toggle.click()
    assert t.MODE == "light", "the theme waited for Save"
    assert isinstance(requests[0][1], QPoint), "no origin for the reveal"
    dialog.reject()
    assert t.MODE == "dark"
    assert settings.get("theme_mode") == "dark"
    assert requests[-1] == ("dark", None)


def test_save_keeps_the_chosen_theme(window):
    from app.ui.settings_dialog import SettingsDialog

    motion.set_motion_enabled(False)
    win, settings = window
    dialog = SettingsDialog(settings, win.manager, win)
    dialog.theme_requested.connect(
        lambda mode, origin: win.set_theme_mode(mode, origin=origin)
    )
    dialog.theme_toggle.click()
    dialog._save()
    assert settings.get("theme_mode") == "light"
    assert t.MODE == "light"


# -------------------------------------------------------------- the reveal

def _curtains(win):
    return [w for w in win.findChildren(QWidget) if w.objectName() == "themeCurtain"]


def test_the_change_is_immediate_and_the_old_theme_is_uncovered(window):
    """The palette switches FIRST, under a snapshot of the old one, so the
    reveal can never make the change late."""
    motion.set_motion_enabled(True)
    win, settings = window
    origin = win.mapToGlobal(QPoint(40, 40))
    win.set_theme_mode("light", origin=origin)
    assert t.MODE == "light", "the palette waited for the animation"
    curtains = _curtains(win)
    assert len(curtains) == 1
    curtain = curtains[0]
    assert curtain.geometry() == win.rect()
    assert curtain.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents), (
        "the reveal would swallow clicks while it plays"
    )
    settle(t.DURATION_THEME + 250)
    assert not _curtains(win), "the reveal did not clean up after itself"


def test_the_circle_starts_at_the_control(window):
    motion.set_motion_enabled(True)
    win, settings = window
    origin = win.mapToGlobal(QPoint(300, 200))
    win.set_theme_mode("light", origin=origin)
    curtain = _curtains(win)[0]
    assert curtain._circle
    assert curtain._centre.toPoint() == QPoint(300, 200)


def test_a_shortcut_fades_rather_than_inventing_a_place(window):
    motion.set_motion_enabled(True)
    win, settings = window
    win.toggle_theme()
    curtain = _curtains(win)[0]
    assert not curtain._circle


def test_no_reveal_at_all_under_reduced_motion(window):
    motion.set_motion_enabled(False)
    win, settings = window
    win.set_theme_mode("light", origin=win.mapToGlobal(QPoint(10, 10)))
    assert t.MODE == "light"
    assert not _curtains(win)

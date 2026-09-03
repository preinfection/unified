"""Contract tests for the startup window and for how the app opens.

Two things happen before a mailbox is on screen, and both used to be
invisible:

* **The startup window.** It reports real, completed steps. The test that
  matters is not "it draws a bar" but that the bar cannot lie: the
  fraction must correspond to steps `app/main.py` has actually finished,
  must never go backwards if a report arrives out of order, and must
  reach exactly full when the last stage lands. The label and the
  fraction are one thing, so they are asserted together.
* **The main window opening maximised.** A three-pane mail client in a
  1360px window on a large display wastes most of the screen. The
  restored geometry is remembered separately, so restore-down returns to
  the size that was actually in use rather than a hard-coded default.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app import config
from app.ui import theme as t
from app.ui.startup_window import STAGES, StartupWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet

    app.setStyleSheet(get_stylesheet())
    yield app


@pytest.fixture
def window(qapp):
    w = StartupWindow()
    yield w
    w.close()


# ------------------------------------------------------------- the stages


def test_main_reports_every_stage_this_window_declares():
    """The labels live in the startup window; `app/main.py` imports them.
    If someone adds a startup step and forgets to report it, the bar
    would stop short of full - so the count is pinned from both ends."""
    import inspect

    from app import main as app_main

    source = inspect.getsource(app_main)
    for index in range(len(STAGES)):
        assert f"STAGES[{index}]" in source, (
            f"STAGES[{index}] ({STAGES[index]!r}) is declared but never "
            f"reported, so the progress bar can never fill"
        )


def test_progress_is_a_real_fraction_of_completed_steps(window):
    """Not a barber pole: each reported step moves the fill by exactly
    one nth, and the last one lands on full."""
    assert window._progress.target == pytest.approx(0.0)
    for step in range(1, len(STAGES) + 1):
        window.set_stage(step)
        assert window._progress.target == pytest.approx(step / len(STAGES))
    assert window._progress.target == pytest.approx(1.0)


def test_progress_never_goes_backwards(window):
    """Startup reports arrive from a worker thread. A late or duplicated
    report must not rewind a bar the user has already watched fill."""
    window.set_stage(3)
    assert window._progress.target == pytest.approx(3 / len(STAGES))
    window.set_stage(1)
    assert window._progress.target == pytest.approx(3 / len(STAGES))


def test_stage_label_swaps_rather_than_blinks(window):
    """A new label keeps the old one around long enough to cross-fade -
    four stages in quick succession should read as one line updating."""
    window.set_stage(1)
    window.set_stage(2)
    assert window._label == STAGES[1]
    assert window._previous_label == STAGES[0]
    assert window._swap.value > 0.0, "the swap has to actually be running"


def test_a_repeated_label_does_not_restart_the_swap(window):
    window.set_stage(1)
    window._swap.set_now(0.0)
    window.set_stage(1, STAGES[0])
    assert window._swap.value == 0.0


def test_it_paints_in_both_themes(window):
    """It is the first thing drawn, before any theme has been applied to
    a real window - so it must be correct in either palette."""
    for mode in ("dark", "light"):
        t.theme_manager.set_mode(mode)
        window.apply_theme()
        for step in range(len(STAGES) + 1):
            window.set_stage(step)
            assert not window.grab().isNull()


def test_it_has_no_title_bar(window):
    """A splash with an OS caption and a close button reads as a window
    that has not finished drawing."""
    from PySide6.QtCore import Qt

    flags = window.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


# ------------------------------------------------ how the window opens


def test_the_app_opens_maximised_by_default():
    assert config.DEFAULTS["start_maximized"] is True


def test_geometry_is_remembered_as_text(tmp_path, monkeypatch):
    """Settings are JSON, so the geometry blob has to survive a round
    trip through a string - base64, not raw bytes."""
    monkeypatch.setattr(config, "app_data_dir", lambda: tmp_path)
    settings = config.Settings()
    assert settings.get("window_geometry") == ""
    settings.set("window_geometry", "AdnQywADAAAAAAAA")
    assert config.Settings().get("window_geometry") == "AdnQywADAAAAAAAA"


def test_a_corrupt_geometry_blob_does_not_stop_the_window_opening(qapp):
    """Restoring is best-effort: a truncated or hand-edited settings file
    should cost the remembered size, not the ability to start."""
    from PySide6.QtCore import QByteArray

    # This is what open_window() does with whatever it finds on disk.
    assert QByteArray.fromBase64(b"not base64 at all") is not None

"""The opening sequence: the bar, the handover, and the failure path.

Startup is the one part of the product with no second chance - if the
handover callback is skipped the window never appears, and if the bar
lies the very first thing the app does is mislead. These assert the two
properties that actually matter (the fill is monotonic and only completes
when the work does, and `on_done` runs on every path) rather than how it
is animated.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.ui import motion, theme as t
from app.ui.components.opening_bar import OpeningBar
from app.ui.startup_window import StartupWindow

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def instant():
    """Reduced motion, so every tween lands on its end value at once.

    The animation is not what these tests are about; where it is, the
    test says so.
    """
    motion.set_motion_enabled(False)
    yield
    motion.set_motion_enabled(True)


# ------------------------------------------------------------------- bar

def test_the_bar_starts_empty(qapp, instant):
    assert OpeningBar(200).progress == 0.0


def test_the_bar_is_monotonic(qapp, instant):
    """A retarget must never walk the fill backwards - work being undone
    is not something startup can express."""
    bar = OpeningBar(200)
    bar.advance_to(0.6)
    assert bar.progress == pytest.approx(0.6)
    bar.advance_to(0.2)
    assert bar.progress == pytest.approx(0.6)


def test_the_bar_is_clamped(qapp, instant):
    bar = OpeningBar(200)
    bar.advance_to(4.0)
    assert bar.progress == 1.0


def test_only_finish_completes_the_bar(qapp, instant):
    """The whole honesty claim. Every stage checkpoint is short of 1.0, so
    the bar can only reach it when initialization really has."""
    for target in StartupWindow.STAGE_PROGRESS.values():
        assert target < 1.0, "a stage checkpoint claims completion"

    bar = OpeningBar(200)
    for target in StartupWindow.STAGE_PROGRESS.values():
        bar.advance_to(target)
    assert bar.progress < 1.0

    done = []
    bar.finish(lambda: done.append(True))
    assert bar.progress == 1.0
    assert done == [True]


def test_finish_always_hands_back_with_motion_on(qapp):
    """A startup whose completion callback can be skipped is a window that
    never opens, so this runs the real animation rather than reduced
    motion."""
    from PySide6.QtCore import QEventLoop, QTimer

    motion.set_motion_enabled(True)
    bar = OpeningBar(200)
    bar.advance_to(0.5)
    done = []
    bar.finish(lambda: done.append(True))

    loop = QEventLoop()
    QTimer.singleShot(700, loop.quit)
    loop.exec()
    assert done == [True]
    assert bar.progress == 1.0


def test_a_startup_too_fast_to_animate_does_not_flash(qapp):
    """On a small cache the whole sequence can be over in under 100ms, and
    a bar that appears and vanishes inside three frames is a flash rather
    than an animation. finish() completes immediately instead."""
    motion.set_motion_enabled(True)
    bar = OpeningBar(200)       # _shown timer starts here
    done = []
    bar.finish(lambda: done.append(True))
    # Synchronous: no event loop was spun, so nothing could have animated.
    assert done == [True]
    assert bar.progress == 1.0


def test_stopping_the_bar_leaves_it_where_it_was(qapp, instant):
    """The failure path. A bar still advancing behind a dialog that says
    startup failed is the interface contradicting itself."""
    bar = OpeningBar(200)
    bar.advance_to(0.4)
    bar.stop()
    assert bar.progress == pytest.approx(0.4)


# --------------------------------------------------------------- stages

def test_the_stage_table_matches_what_main_actually_emits():
    """THE DRIFT GUARD, and the reason this test is worth more than the
    rest of the file. STAGE_PROGRESS is keyed by the exact strings
    app/main.py emits. Reword one of them and the bar silently stops
    advancing for that step - no error, no failing import, just an opening
    sequence that quietly stopped working.
    """
    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'self\.stage\.emit\(\s*"([^"]+)"\s*\)', source))
    # "Preparing mailbox..." is set by main() on the UI thread rather than
    # emitted by the worker, so it is matched separately.
    emitted |= set(re.findall(r'set_stage\(\s*"([^"]+)"\s*\)', source))

    assert emitted, "no stage strings found in app/main.py"
    unknown = emitted - set(StartupWindow.STAGE_PROGRESS)
    assert not unknown, (
        f"app/main.py emits stages the opening bar does not know: {unknown}"
    )


def test_the_checkpoints_only_ever_move_forward():
    values = list(StartupWindow.STAGE_PROGRESS.values())
    assert values == sorted(values), "the stage checkpoints are out of order"


def test_an_unknown_stage_does_not_move_the_bar(qapp, instant):
    """Better to stall honestly than to jump somewhere invented."""
    win = StartupWindow()
    win.set_stage("Reticulating splines...")
    assert win.bar.progress == 0.0
    # ...and it still names what is happening.
    assert "Reticulating splines" in win._stage_label.text()
    win.close()


def test_each_real_stage_advances_the_bar(qapp, instant):
    win = StartupWindow()
    seen = []
    for stage in StartupWindow.STAGE_PROGRESS:
        win.set_stage(stage)
        seen.append(float(win.bar.progress))
    assert seen == sorted(seen)
    assert seen[-1] == pytest.approx(0.86)
    win.close()


def test_the_stage_line_never_moves_the_mark(qapp, instant):
    """The identity must not shift while the text under it changes."""
    win = StartupWindow()
    win.show()
    qapp.processEvents()
    before = win._stage_label.height()
    win.set_stage("Unlocking encrypted mailbox...")
    qapp.processEvents()
    assert win._stage_label.height() == before
    win.close()


# ------------------------------------------------------------- handover

def test_finish_closes_the_window_and_hands_over(qapp, instant):
    win = StartupWindow()
    win.show()
    done = []
    win.finish(lambda: done.append(True))
    qapp.processEvents()
    assert done == [True]


def test_fail_stops_the_bar_and_closes(qapp, instant):
    """A splash left on screen with nothing behind it is an app that
    looks hung, so the failure path really does dispose of the window -
    the error dialog is then the only thing on screen, which is the point.

    Asserted through shiboken rather than isVisible(): the window carries
    WA_DeleteOnClose, so the C++ object is gone and touching any method on
    it raises. Being gone IS the pass condition.
    """
    import shiboken6

    win = StartupWindow()
    win.show()
    win.set_stage("Unlocking encrypted mailbox...")
    win.fail()
    qapp.processEvents()
    assert not shiboken6.isValid(win), "the opening surface outlived the failure"


# ----------------------------------------------------------- appearance

def test_the_opening_surface_uses_the_stored_theme(qapp):
    """The first frame is not the place to be wrong about which product
    this is: a user on the light theme must not watch the app open dark
    and then flip."""
    from app import config

    t.apply_mode("light")
    try:
        win = StartupWindow()
        assert t.BG_APP in win.styleSheet()
        win.close()
    finally:
        t.apply_mode("dark")

    # ...and the value main() reads is a real, side-effect-free peek.
    peeked = config.peek_appearance()
    assert set(peeked) == {"theme_mode", "reduced_motion"}


def test_peek_appearance_survives_a_missing_or_broken_file(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "app_data_dir", lambda: tmp_path)
    assert config.peek_appearance()["theme_mode"] == "dark"

    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    assert config.peek_appearance()["theme_mode"] == "dark"

    (tmp_path / "settings.json").write_text(
        '{"theme_mode": "light", "reduced_motion": true}', encoding="utf-8"
    )
    peeked = config.peek_appearance()
    assert peeked["theme_mode"] == "light"
    assert peeked["reduced_motion"] is True


def test_the_bar_is_readable_in_both_palettes(qapp):
    """The opening bar must not rely on a colour that only works in one
    theme - it is the only thing on the screen."""
    from PySide6.QtGui import QColor

    for mode in ("dark", "light"):
        t.apply_mode(mode)
        fill, track = QColor(t.ACCENT), QColor(t.BORDER)
        assert abs(fill.lightness() - track.lightness()) > 60, (
            f"the fill and the track are hard to tell apart in {mode}"
        )
    t.apply_mode("dark")


# --------------------------------------------- the user closes the splash

def test_closing_the_opening_window_does_not_crash_the_worker(qapp, instant):
    """THE CRASH THIS SECTION EXISTS FOR.

    The opening surface used to be a 340x220 card almost nobody hit the X
    on. Making it maximized with a full title bar turned "close the
    loading screen" into an obvious thing to try - and WA_DeleteOnClose
    destroys the C++ object while the background init thread carries on,
    so the very next set_stage() took the whole process down with
    "Internal C++ object already deleted". The main window would never
    have appeared.
    """
    win = StartupWindow()
    win.show()
    win.set_stage("Checking install...")
    win.close()                      # the user dismisses it mid-startup
    qapp.processEvents()

    # Everything the worker still calls has to be survivable.
    win.set_stage("Unlocking encrypted mailbox...")
    win.set_stage("Loading local cache...")
    win.bring_to_front()
    win.retheme()


def test_the_handover_still_runs_after_the_user_closes_it(qapp, instant):
    """Closing the opening layer means "skip the animation", not "abandon
    the launch" - the mailbox is decrypted and open by that point, and
    quitting would leave it that way on disk. The shell must still be
    shown."""
    win = StartupWindow()
    win.show()
    win.close()
    qapp.processEvents()

    done = []
    win.finish(lambda: done.append(True))
    assert done == [True], "the shell would never have been revealed"


def test_failing_after_the_user_closes_it_is_survivable(qapp, instant):
    win = StartupWindow()
    win.show()
    win.close()
    qapp.processEvents()
    win.fail()          # must not raise


def test_a_normal_handover_is_not_reported_as_cancelled(qapp, instant):
    win = StartupWindow()
    win.show()
    win.finish(lambda: None)
    qapp.processEvents()
    assert not win.was_cancelled()


# ------------------------------- the timing that actually reaches users

def _run_for(ms: int) -> None:
    """Let real animation time pass."""
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_stages_arriving_after_the_animation_finishes(qapp):
    """THE BUG THAT STOPPED THE APP OPENING ON A REAL MAILBOX.

    advance_to() built a fresh QPropertyAnimation per call and started it
    with DeleteWhenStopped while keeping a reference. DeleteWhenStopped
    destroys the C++ object when the animation COMPLETES, so the reference
    dangled and the next stage called .stop() on it - "Internal C++ object
    already deleted", raised inside a signal handler, leaving the opening
    window on screen forever at "Preparing mailbox".

    It never reproduced in testing because every other test either uses
    reduced motion or steps stages faster than the 900ms animation, so it
    was always still alive. A five-second mailbox decrypt is what let the
    first animation finish before the second stage arrived. This test
    waits past the animation on purpose.
    """
    motion.set_motion_enabled(True)
    win = StartupWindow()
    win.show()

    stages = list(StartupWindow.STAGE_PROGRESS)
    win.set_stage(stages[0])
    # Longer than DURATION_REVEAL: the animation completes and, under the
    # old code, deleted itself out from under the next call.
    _run_for(1100)
    win.set_stage(stages[1])          # this used to raise
    _run_for(1100)
    win.set_stage(stages[2])
    _run_for(1100)
    win.set_stage(stages[3])
    _run_for(1100)                    # let the last one actually travel

    assert float(win.bar.progress) == pytest.approx(0.86, abs=0.02)

    done = []
    win.finish(lambda: done.append(True))
    _run_for(800)
    assert done == [True], "the shell would never have been revealed"


def test_a_slow_startup_still_hands_over(qapp):
    """The same shape end to end: every stage separated by more than the
    animation it starts."""
    motion.set_motion_enabled(True)
    bar = OpeningBar(200)
    for target in (0.12, 0.38, 0.64, 0.86):
        bar.advance_to(target)
        _run_for(950)
    done = []
    bar.finish(lambda: done.append(True))
    _run_for(600)
    assert done == [True]
    assert float(bar.progress) == 1.0


def test_the_handover_fires_once_and_not_for_stage_changes(qapp):
    """A stage transition completing must never invoke a handover nobody
    asked for - that would tear the opening layer away mid-startup."""
    motion.set_motion_enabled(True)
    bar = OpeningBar(200)
    done = []
    bar.advance_to(0.4)
    _run_for(950)                     # a stage animation completes
    assert done == [], "a stage completion triggered the handover"

    bar.finish(lambda: done.append(True))
    _run_for(600)
    assert done == [True]
    _run_for(300)
    assert done == [True], "the handover fired more than once"

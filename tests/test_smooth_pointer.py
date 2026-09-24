"""The experimental smoothed pointer: off by default, and out of the way
wherever precision matters.

A smoothed pointer is behind the real one by construction; these tests
guard that it is opt-in, that it hands the native pointer back over text,
handles, drags and outside the app, that it leaves the override-cursor
stack balanced, and that its lag is what the code says it is.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.ui import motion
from app.ui.smooth_pointer import SmoothPointer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def scene(qapp):
    host = QWidget()
    col = QVBoxLayout(host)
    button = QPushButton("Button")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    field = QLineEdit()
    text = QTextEdit()
    splitter = QSplitter()
    splitter.addWidget(QWidget())
    splitter.addWidget(QWidget())
    for w in (button, field, text, splitter):
        col.addWidget(w)
    host.resize(400, 400)
    host.show()
    qapp.processEvents()
    pointer = SmoothPointer()
    yield host, button, field, text, splitter, pointer
    pointer.shutdown()
    host.close()
    motion.set_motion_enabled(True)
    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()


def move(host, widget, buttons=Qt.MouseButton.NoButton):
    point = QPointF(widget.mapTo(host, widget.rect().center()))
    event = QMouseEvent(QEvent.Type.MouseMove, point,
                        QPointF(host.mapToGlobal(point.toPoint())),
                        Qt.MouseButton.NoButton, buttons,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(host.windowHandle(), event)


def test_it_is_off_unless_chosen():
    assert config.DEFAULTS["smooth_pointer"] is False
    assert not SmoothPointer().is_enabled()


def test_it_follows_over_ordinary_controls(scene):
    host, button, *_, pointer = scene
    pointer.set_enabled(True)
    move(host, button)
    assert pointer.is_following()
    assert QApplication.overrideCursor().shape() == Qt.CursorShape.BlankCursor


def test_text_gets_the_native_i_beam(scene):
    host, button, field, text, splitter, pointer = scene
    pointer.set_enabled(True)
    move(host, button)
    move(host, field)
    assert not pointer.is_following()
    assert QApplication.overrideCursor() is None
    move(host, text)
    assert QApplication.overrideCursor() is None


def test_a_held_button_gets_the_native_pointer(scene):
    """Drags, selections and the press itself are where precision is owed."""
    host, button, *_, pointer = scene
    pointer.set_enabled(True)
    move(host, button)
    move(host, button, Qt.MouseButton.LeftButton)
    assert not pointer.is_following()
    assert QApplication.overrideCursor() is None


def test_a_press_snaps_back_to_native_at_once(scene):
    host, button, *_, pointer = scene
    pointer.set_enabled(True)
    move(host, button)
    point = QPointF(button.mapTo(host, button.rect().center()))
    QApplication.sendEvent(host.windowHandle(), QMouseEvent(
        QEvent.Type.MouseButtonPress, point, QPointF(host.mapToGlobal(point.toPoint())),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    ))
    assert not pointer.is_following()


def test_handles_keep_their_own_cursors(scene):
    host, button, field, text, splitter, pointer = scene
    handle = splitter.handle(1)
    assert SmoothPointer.wants_native(handle, Qt.MouseButton.NoButton)


def test_leaving_the_app_restores_the_system_pointer(scene):
    host, button, *_, pointer = scene
    pointer.set_enabled(True)
    move(host, button)
    QApplication.sendEvent(host.windowHandle(), QEvent(QEvent.Type.Leave))
    assert not pointer.is_following()
    assert QApplication.overrideCursor() is None


def test_reduced_motion_turns_it_off(scene):
    host, button, *_, pointer = scene
    pointer.set_enabled(True)
    motion.set_motion_enabled(False)
    move(host, button)
    assert not pointer.is_following()
    assert QApplication.overrideCursor() is None


def test_disabling_mid_follow_leaves_the_cursor_stack_balanced(scene):
    host, button, *_, pointer = scene
    pointer.set_enabled(True)
    for _ in range(5):
        move(host, button)          # repeated moves must not stack overrides
    pointer.set_enabled(False)
    assert QApplication.overrideCursor() is None


def test_the_lag_is_what_the_documentation_says():
    """Measured, so the setting's description cannot quietly go stale."""
    assert SmoothPointer.tracking_lag_ms() == pytest.approx(54, abs=2)
    assert SmoothPointer.settle_time_ms(200) == pytest.approx(205, abs=15)

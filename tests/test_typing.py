"""App-written text typed in; user-written text never animated.

The reveal exists for exactly one case - the quoted original a reply or
forward inserts - and these tests guard the promises that make it safe:
the whole text is in the document from the first frame, the user's first
input ends the reveal at once and still lands where the user meant, and
reduced motion means no reveal at all.
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QEventLoop, QMimeData, QPointF, Qt, QTimer
from PySide6.QtGui import QInputMethodEvent, QKeyEvent, QMouseEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from app.ui import motion
from app.ui.components.typing import TypingTextEdit

QUOTE = "\n\nOn 1 Oct 2026 at 10:00, Ada wrote:\n> line one\n> line two\n> line three\n"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def settle(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture()
def edit(qapp):
    motion.set_motion_enabled(True)
    widget = TypingTextEdit()
    widget.setPlainText(QUOTE)
    widget.resize(500, 300)
    widget.show()
    widget.moveCursor(QTextCursor.MoveOperation.Start)
    qapp.processEvents()
    yield widget
    widget.close()
    motion.set_motion_enabled(True)


def test_it_types_in_and_finishes_by_itself(edit):
    assert edit.type_in(0)
    first = edit.revealed_until()
    assert first == QUOTE.index("On"), "blank lines were 'typed' as a delay"
    settle(150)
    middle = edit.revealed_until()
    assert first < middle < len(QUOTE), "it did not type progressively"
    deadline = time.monotonic() + 2
    while edit.is_typing() and time.monotonic() < deadline:
        settle(20)
    assert not edit.is_typing(), "the reveal never ended"


def test_the_whole_text_is_there_from_the_first_frame(edit):
    """The reveal is a mask: sending or copying mid-reveal gets everything."""
    edit.type_in(0)
    assert edit.is_typing()
    assert edit.toPlainText() == QUOTE


def test_it_adds_nothing_to_undo(edit):
    edit.type_in(0)
    edit.finish_typing()
    assert not edit.document().isUndoAvailable()


def _key(widget, key, text=""):
    QApplication.sendEvent(
        widget, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)
    )


def test_a_keystroke_ends_it_at_once_and_lands_at_the_users_cursor(edit):
    edit.type_in(0)
    assert edit.is_typing()
    _key(edit, Qt.Key.Key_H, "H")
    assert not edit.is_typing(), "the app kept typing against the user"
    assert edit.toPlainText() == "H" + QUOTE, "the keystroke went into the quote"


def test_a_click_ends_it(edit):
    edit.type_in(0)
    point = QPointF(5, 5)
    QApplication.sendEvent(edit.viewport(), QMouseEvent(
        QEvent.Type.MouseButtonPress, point, edit.viewport().mapToGlobal(point),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    ))
    assert not edit.is_typing()


def test_a_paste_ends_it_and_is_not_animated(edit):
    edit.type_in(0)
    data = QMimeData()
    data.setText("pasted")
    edit.insertFromMimeData(data)
    assert not edit.is_typing()
    assert edit.toPlainText().startswith("pasted")


def test_ime_composition_ends_it(edit):
    edit.type_in(0)
    QApplication.sendEvent(edit, QInputMethodEvent("ka", []))
    assert not edit.is_typing()


def test_the_users_own_typing_is_never_animated(edit):
    for char in "Hello":
        _key(edit, getattr(Qt.Key, f"Key_{char.upper()}"), char)
    assert not edit.is_typing()
    assert edit.toPlainText().startswith("Hello")


def test_nothing_is_animated_under_reduced_motion(edit):
    motion.set_motion_enabled(False)
    assert not edit.type_in(0)
    assert not edit.is_typing()
    assert edit.revealed_until() == len(QUOTE)


def test_a_reply_types_its_quote_in_and_a_new_message_does_not(qapp):
    from app.ui.compose_dialog import ComposeDialog

    accounts = [{"id": 1, "email": "me@example.org", "provider": "gmail"}]
    reply = ComposeDialog(accounts, mode="reply", to="ada@example.org",
                          subject="Re: x", body=QUOTE)
    reply.show()
    settle(30)
    assert reply.body_edit.is_typing()
    reply.body_edit.finish_typing()
    reply.done(0)

    fresh = ComposeDialog(accounts)
    fresh.show()
    settle(30)
    assert not fresh.body_edit.is_typing()
    fresh.done(0)


def test_sending_mid_reveal_sends_the_whole_quote(qapp, monkeypatch):
    from app.ui import compose_dialog as module

    captured = {}

    class _Worker:
        def __init__(self, account, to, subject, body, cc="", bcc="", parent=None):
            captured["body"] = body
            self.succeeded = self.failed = type("S", (), {"connect": lambda *a: None})()

        def start(self):
            pass

        def isRunning(self):
            return False

    monkeypatch.setattr(module, "_SendWorker", _Worker)
    accounts = [{"id": 1, "email": "me@example.org", "provider": "gmail"}]
    dialog = module.ComposeDialog(accounts, mode="reply", to="ada@example.org",
                                  subject="Re: x", body=QUOTE)
    dialog.show()
    settle(30)
    assert dialog.body_edit.is_typing()
    dialog._on_send()
    assert captured["body"] == QUOTE
    assert not dialog.body_edit.is_typing()
    dialog._sending = False
    dialog.done(0)

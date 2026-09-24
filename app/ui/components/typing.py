"""Text the APP writes, appearing as if typed - and never text the user
writes.

ADAPTED FROM MAGIC UI'S TYPING ANIMATION, which reveals a string one
character at a time behind a caret. The reason it works is that it
separates "text that is being put here" from "text that was already
here": the eye follows the writing and knows where it came from.

In a mail client there is exactly one place where the application writes
into the user's document: reply and forward insert the quoted original
under the cursor. That is the only use here. The user's own keystrokes,
IME composition and pasted text are never animated - they go straight in,
as ever.

HOW IT STAYS HONEST AND SAFE

  * THE TEXT IS ALL THERE FROM THE START. The document holds the complete
    quote before the first frame; the reveal is a mask painted over the
    part not yet "typed". Sending, copying, saving or reading
    toPlainText() mid-reveal therefore always sees the whole message -
    the animation cannot lose or delay a character of it, and it adds
    nothing to the undo history.
  * IT YIELDS AT ONCE. The first key, click, paste, IME event or wheel
    tick finishes the reveal immediately and then goes where it was
    going. The user is never made to wait for, or type against, the app.
  * IT IS SHORT. The attribution line is typed at a writing pace, then the
    quoted body arrives a few lines at a time: well under a second even
    for a long message, because the body is context, not the point.
  * REDUCED MOTION: the text is simply there.
"""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from app.ui import motion, theme as t

# Writing pace for the first line, and the budget it may take.
CHAR_MS = 9
FIRST_LINE_BUDGET_MS = 360
# Then the rest, line by line, within its own budget.
LINE_MS = 22
REST_BUDGET_MS = 300
_FRAME_MS = 16


class TypingTextEdit(QPlainTextEdit):
    """A QPlainTextEdit that can type in app-inserted text from a position
    to the end of the document."""

    typing_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start = -1          # first character being revealed
        self._shown = -1          # reveal position; -1 = not revealing
        self._first_line_end = 0
        self._line_ends: list[int] = []
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick)
        # The colour the mask paints: whatever the text sits on.
        self.mask_colour = lambda: t.BG_APP

    # ------------------------------------------------------------------ api

    def type_in(self, start: int) -> bool:
        """Reveal everything from `start` to the end as if typed. Returns
        False (and shows it all) when there is nothing to animate or
        motion is off."""
        text = self.toPlainText()
        # Skip leading blank lines: they are where the user will write,
        # and "typing" whitespace just looks like a delay.
        while start < len(text) and text[start] in "\n\r \t":
            start += 1
        if start >= len(text) or not motion.motion_enabled():
            self.finish_typing()
            return False
        self._start = start
        self._shown = start
        first = text.find("\n", start)
        self._first_line_end = len(text) if first < 0 else first + 1
        self._line_ends = []
        pos = self._first_line_end
        while pos < len(text):
            nxt = text.find("\n", pos)
            pos = len(text) if nxt < 0 else nxt + 1
            self._line_ends.append(pos)
        self._clock.start()
        self._timer.start()
        self.viewport().update()
        return True

    def is_typing(self) -> bool:
        return self._shown >= 0

    def revealed_until(self) -> int:
        return self._shown if self._shown >= 0 else len(self.toPlainText())

    def finish_typing(self) -> None:
        was = self._shown >= 0
        self._timer.stop()
        self._shown = -1
        self.viewport().update()
        if was:
            self.typing_finished.emit()

    # ---------------------------------------------------------------- timing

    def _position_at(self, ms: float) -> int:
        chars = self._first_line_end - self._start
        first_ms = min(FIRST_LINE_BUDGET_MS, chars * CHAR_MS)
        if ms < first_ms and first_ms > 0:
            return self._start + int(chars * ms / first_ms)
        if not self._line_ends:
            return self._first_line_end
        rest_ms = min(REST_BUDGET_MS, len(self._line_ends) * LINE_MS)
        done = (ms - first_ms) / rest_ms if rest_ms else 1.0
        if done >= 1.0:
            return self._line_ends[-1]
        index = int(len(self._line_ends) * done)
        return self._line_ends[index - 1] if index > 0 else self._first_line_end

    def _tick(self) -> None:
        end = len(self.toPlainText())
        position = self._position_at(self._clock.elapsed())
        if position >= end:
            self.finish_typing()
            return
        if position != self._shown:
            self._shown = position
            self.viewport().update()

    # ------------------------------------------------------------ the mask

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._shown < 0:
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(min(self._shown, len(self.toPlainText())))
        caret = self.cursorRect(cursor)
        view = self.viewport().rect()
        colour = QColor(self.mask_colour())
        painter = QPainter(self.viewport())
        # The rest of the current line, then everything below it.
        painter.fillRect(QRect(caret.left(), caret.top(),
                               view.right() - caret.left() + 1, caret.height()),
                         colour)
        painter.fillRect(QRect(view.left(), caret.bottom() + 1,
                               view.width(), max(0, view.bottom() - caret.bottom())),
                         colour)
        painter.end()

    # --------------------------------------------------- yield to the user

    def keyPressEvent(self, event) -> None:  # noqa: N802
        self.finish_typing()
        super().keyPressEvent(event)

    def inputMethodEvent(self, event) -> None:  # noqa: N802
        self.finish_typing()
        super().inputMethodEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.finish_typing()
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        self.finish_typing()
        super().wheelEvent(event)

    def insertFromMimeData(self, source) -> None:  # noqa: N802
        self.finish_typing()
        super().insertFromMimeData(source)

"""A small colored dot + text label, used for per-account sync status.

Reused by AccountItem (sidebar) and LoadingState (center panel) so a
given status always renders with the same color and never needs a widget
subclass of its own at each call site.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.ui import theme as t

_DOT_SIZE = 8


class StatusIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = QLabel()
        self._dot.setFixedSize(_DOT_SIZE, _DOT_SIZE)
        self._text = QLabel()
        self._text.setObjectName("tertiary")
        self._text.setWordWrap(False)

        layout.addWidget(self._dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._text, stretch=1)
        self._status_key = "idle"
        self._suppressed = False
        self.set_status("idle", "")

    def set_status(self, status_key: str, text: str) -> None:
        self._status_key = status_key
        color = t.STATUS_COLORS.get(status_key, t.TEXT_TERTIARY)
        self._dot.setStyleSheet(
            f"background: {color}; border-radius: {_DOT_SIZE // 2}px;"
        )
        self._text.setText(text)
        self._dot.setVisible(bool(text))
        self._refresh_visibility()

    def set_suppressed(self, suppressed: bool) -> None:
        """Hide this regardless of whether it has anything to say.

        THIS EXISTS BECAUSE set_status USED TO OWN setVisible OUTRIGHT, and
        that quietly defeated the collapsed sidebar. AccountItem hid the
        status line when the drawer became a rail; the very next sync
        progress tick - and those arrive several times a second while
        syncing - called set_status, saw it had text, and showed it again.
        A status dot reappeared beside every avatar in a 56px rail a few
        hundred milliseconds after collapsing, with nothing the user had
        done to explain it. Two owners of one visibility flag, and the one
        that fired most often won.
        """
        self._suppressed = bool(suppressed)
        self._refresh_visibility()

    def _refresh_visibility(self) -> None:
        self.setVisible(bool(self._text.text()) and not self._suppressed)

    def retheme(self) -> None:
        """The dot's colour lives in an inline stylesheet because it is a
        painted swatch rather than text, so it has to be restated when the
        palette moves."""
        self.set_status(self._status_key, self._text.text())

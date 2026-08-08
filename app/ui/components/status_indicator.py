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
        self.set_status("idle", "")

    def set_status(self, status_key: str, text: str) -> None:
        color = t.STATUS_COLORS.get(status_key, t.TEXT_TERTIARY)
        self._dot.setStyleSheet(
            f"background: {color}; border-radius: {_DOT_SIZE // 2}px;"
        )
        self._text.setText(text)
        self._dot.setVisible(bool(text))
        self.setVisible(bool(text))

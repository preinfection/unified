"""Reusable centered loading/empty-state panel: shown in the message list
area while an account has no cached rows yet (initial sync, waiting in
the sync queue). Pure presentation - MainWindow still decides what text
and progress numbers to show based on sync state.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class LoadingState(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.addStretch(2)

        inner = QVBoxLayout()
        inner.setSpacing(10)
        self._account_label = QLabel("")
        self._account_label.setObjectName("heading")
        self._account_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bar = QProgressBar()
        self._bar.setFixedWidth(360)
        self._bar.setTextVisible(False)
        self._detail_label = QLabel("")
        self._detail_label.setObjectName("secondary")
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        inner.addWidget(self._account_label)
        inner.addWidget(self._status_label)
        inner.addWidget(self._bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        inner.addWidget(self._detail_label)
        outer.addLayout(inner)
        outer.addStretch(3)

    def set_state(
        self, account_email: str, status_text: str, detail_text: str,
        done: int = 0, total: int = 0,
    ) -> None:
        self._account_label.setText(account_email)
        self._status_label.setText(status_text)
        self._detail_label.setText(detail_text)
        if total:
            self._bar.setRange(0, total)
            self._bar.setValue(done)
        else:
            self._bar.setRange(0, 0)  # indeterminate busy indicator

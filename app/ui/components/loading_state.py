"""Reusable centered loading/empty-state panel: shown in the message list
area while an account has no cached rows yet (initial sync, waiting in
the sync queue). Pure presentation - MainWindow still decides what text
and progress numbers to show based on sync state.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from app.ui import theme as t


class LoadingState(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.addStretch(2)

        inner = QVBoxLayout()
        inner.setSpacing(t.SPACE_SM + 2)
        self._account_label = QLabel("")
        self._account_label.setFont(t.make_font("dialog_heading"))
        self._account_label.setStyleSheet(f"color: {t.TEXT_PRIMARY};")
        self._account_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label = QLabel("")
        self._status_label.setFont(t.make_font("body"))
        self._status_label.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bar = QProgressBar()
        self._bar.setFixedWidth(360)
        self._bar.setTextVisible(False)
        self._detail_label = QLabel("")
        self._detail_label.setFont(t.make_font("caption"))
        self._detail_label.setStyleSheet(f"color: {t.TEXT_TERTIARY};")
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        inner.addWidget(self._account_label)
        inner.addWidget(self._status_label)
        inner.addSpacing(t.SPACE_XS)
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

"""Collapsible developer console: filtered monospace log pane fed by logging.

A logging.Handler forwards every INFO+ record through a Qt signal, so
messages logged from worker threads land safely on the UI thread. Records
are kept with a category (SYNC / DATABASE / API / other) derived from the
logger name so the pane can be filtered. Secrets never appear because the
app never logs tokens or passwords.
"""

from __future__ import annotations

import logging
from collections import deque

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme as t
from app.ui.components.buttons import Button

MAX_RECORDS = 3000

CAT_SYNC = "SYNC"
CAT_DB = "DATABASE"
CAT_API = "API"
CAT_OTHER = "APP"

FILTERS = ["ALL", CAT_SYNC, "ERRORS", CAT_DB, CAT_API]


def categorize(logger_name: str) -> str:
    if "sync_service" in logger_name or "account_manager" in logger_name:
        return CAT_SYNC
    if "database" in logger_name:
        return CAT_DB
    if any(part in logger_name for part in
           ("gmail", "imap", "smtp", "oauth", "googleapiclient", "auth")):
        return CAT_API
    return CAT_OTHER


class _LogBridge(QObject):
    record = Signal(str, int, str)  # category, levelno, formatted text


class QtLogHandler(logging.Handler):
    def __init__(self, bridge: _LogBridge):
        super().__init__(level=logging.INFO)
        self.bridge = bridge
        self.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.bridge.record.emit(
                categorize(record.name), record.levelno, self.format(record)
            )
        except RuntimeError:
            pass  # bridge destroyed during shutdown


class ConsoleWidget(QWidget):
    """Square, thin-bordered log pane with filter/clear/copy/auto-scroll."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # (category, levelno, text) ring buffer; source of truth for re-filters
        self._records: deque[tuple[str, int, str]] = deque(maxlen=MAX_RECORDS)
        self._filter = "ALL"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        controls = QHBoxLayout()
        controls.setContentsMargins(
            t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD
        )
        controls.setSpacing(t.SPACE_SM)

        heading = QLabel("Console")
        heading.setProperty("role", "overline")
        heading.setFont(t.make_font("overline"))
        controls.addWidget(heading)
        controls.addSpacing(t.SPACE_MD)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        for name in FILTERS:
            btn = QPushButton(name.title() if name != "ALL" else "All")
            btn.setObjectName("consoleFilter")
            btn.setFont(t.make_font("caption_strong"))
            btn.setCheckable(True)
            btn.setChecked(name == "ALL")
            btn.clicked.connect(lambda _=False, n=name: self._set_filter(n))
            self._filter_group.addButton(btn)
            controls.addWidget(btn)
        controls.addStretch(1)

        self.autoscroll_check = QCheckBox("Auto-scroll")
        self.autoscroll_check.setChecked(True)
        self.autoscroll_check.setFont(t.make_font("caption"))
        controls.addWidget(self.autoscroll_check)

        copy_btn = Button("Copy", variant="subtle", size="sm", icon="download",
                          tooltip="Copy the visible log to the clipboard")
        copy_btn.clicked.connect(self._copy)
        controls.addWidget(copy_btn)

        clear_btn = Button("Clear", variant="subtle", size="sm", icon="close",
                           tooltip="Clear the console")
        clear_btn.clicked.connect(self._clear)
        controls.addWidget(clear_btn)

        layout.addLayout(controls)

        self.view = QPlainTextEdit()
        self.view.setObjectName("console")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(MAX_RECORDS)
        self.view.setPlaceholderText(
            "Console - sync activity and errors appear here"
        )
        layout.addWidget(self.view, stretch=1)

        self._bridge = _LogBridge()
        self._bridge.record.connect(self._on_record)
        self._handler = QtLogHandler(self._bridge)
        logging.getLogger().addHandler(self._handler)

    # -------------------------------------------------------------- filtering

    def _matches(self, category: str, level: int) -> bool:
        if self._filter == "ALL":
            return True
        if self._filter == "ERRORS":
            return level >= logging.WARNING
        return category == self._filter

    def _set_filter(self, name: str) -> None:
        self._filter = name
        self.view.setPlainText(
            "\n".join(t for c, lvl, t in self._records if self._matches(c, lvl))
        )
        self._scroll_to_bottom()

    def _on_record(self, category: str, level: int, text: str) -> None:
        self._records.append((category, level, text))
        if not self._matches(category, level):
            return
        bar = self.view.verticalScrollBar()
        keep_pos = bar.value()
        self.view.appendPlainText(text)
        if self.autoscroll_check.isChecked():
            self._scroll_to_bottom()
        else:
            bar.setValue(keep_pos)

    def _scroll_to_bottom(self) -> None:
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------------------------------------------------------------- actions

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.view.toPlainText())

    def _clear(self) -> None:
        self._records.clear()
        self.view.clear()

    # convenience for the main window
    def toPlainText(self) -> str:  # noqa: N802 (Qt naming kept for callers)
        return self.view.toPlainText()

    def detach(self) -> None:
        logging.getLogger().removeHandler(self._handler)

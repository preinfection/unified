"""Collapsible developer console: a plain monospace log pane fed by logging.

A logging.Handler forwards every INFO+ record through a Qt signal, so
messages logged from worker threads land safely on the UI thread. Secrets
never appear because the app never logs tokens or passwords.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QPlainTextEdit

MAX_LINES = 2000


class _LogBridge(QObject):
    message = Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, bridge: _LogBridge):
        super().__init__(level=logging.INFO)
        self.bridge = bridge
        self.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.bridge.message.emit(self.format(record))
        except RuntimeError:
            pass  # bridge destroyed during shutdown


class ConsoleWidget(QPlainTextEdit):
    """Read-only monospace log view (square corners, thin border via QSS)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("console")
        self.setReadOnly(True)
        self.setMaximumBlockCount(MAX_LINES)
        self.setPlaceholderText("Console - sync activity and errors appear here")

        self._bridge = _LogBridge()
        self._bridge.message.connect(self.appendPlainText)
        self._handler = QtLogHandler(self._bridge)
        logging.getLogger().addHandler(self._handler)

    def detach(self) -> None:
        logging.getLogger().removeHandler(self._handler)

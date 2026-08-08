"""Top action bar: Compose (primary), Refresh, Console toggle, search.

A thin QToolBar wrapper so main_window.py wires up signals instead of
building widgets inline - the toolbar's own construction logic lives in
one place and is easy to re-style without touching MainWindow.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QPushButton, QSizePolicy, QToolBar, QWidget


class TopToolBar(QToolBar):
    compose_clicked = Signal()
    refresh_clicked = Signal()
    console_toggled = Signal(bool)
    search_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(False)

        compose_btn = QPushButton("✎  Compose")
        compose_btn.setObjectName("composeButton")
        compose_btn.clicked.connect(self.compose_clicked.emit)
        self.addWidget(compose_btn)

        refresh_btn = QPushButton("⟳  Refresh")
        refresh_btn.setObjectName("iconButton")
        refresh_btn.clicked.connect(self.refresh_clicked.emit)
        self.addWidget(refresh_btn)

        self.console_btn = QPushButton("☷  Console")
        self.console_btn.setObjectName("iconButton")
        self.console_btn.setCheckable(True)
        self.console_btn.toggled.connect(self.console_toggled.emit)
        self.addWidget(self.console_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search all accounts...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(320)
        self.search_edit.textChanged.connect(self.search_changed.emit)
        self.addWidget(self.search_edit)

    def set_search_placeholder(self, text: str) -> None:
        self.search_edit.setPlaceholderText(text)

    def search_text(self) -> str:
        return self.search_edit.text().strip()

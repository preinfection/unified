"""Top action bar: Compose (primary), Refresh, Console toggle, search.

Refresh and Console are icon-only with tooltips, matching how native
desktop mail clients (Mail.app, Outlook) treat secondary toolbar actions -
icon+text on every button reads as a web toolbar, not a native one.
Compose keeps its label since it's the one primary action worth spelling
out. All icons are real SVG assets tinted per Qt icon Mode (Normal/
Active/Selected/Disabled), never Unicode glyphs.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QLineEdit, QPushButton, QSizePolicy, QToolBar, QWidget

from app.ui import theme as t
from app.ui.svg_icon import icon_set, simple_icon

_ICON_SIZE = 18


def _icon_button(icon_name: str, tooltip: str, *, checkable: bool = False) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("iconButton")
    btn.setToolTip(tooltip)
    btn.setCheckable(checkable)
    btn.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
    btn.setIcon(icon_set(
        icon_name, _ICON_SIZE,
        normal=t.ICON_SECONDARY, active=t.ICON_ACTIVE,
        selected=t.ICON_SELECTED, disabled=t.ICON_DISABLED,
    ))
    btn.setFixedSize(34, 34)
    return btn


class TopToolBar(QToolBar):
    compose_clicked = Signal()
    refresh_clicked = Signal()
    console_toggled = Signal(bool)
    search_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(False)

        compose_btn = QPushButton(" Compose")
        compose_btn.setObjectName("composeButton")
        compose_btn.setIcon(simple_icon("compose", 16, t.TEXT_ON_ACCENT))
        compose_btn.setIconSize(QSize(16, 16))
        compose_btn.clicked.connect(self.compose_clicked.emit)
        self.addWidget(compose_btn)

        self.addSeparator()

        refresh_btn = _icon_button("refresh", "Refresh (sync all accounts)")
        refresh_btn.clicked.connect(self.refresh_clicked.emit)
        self.addWidget(refresh_btn)

        self.console_btn = _icon_button("console", "Show/hide developer console",
                                        checkable=True)
        self.console_btn.toggled.connect(self.console_toggled.emit)
        self.addWidget(self.console_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText("Search all accounts...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(320)
        self.search_edit.addAction(
            simple_icon("search", 15, t.TEXT_TERTIARY), QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search_edit.textChanged.connect(self.search_changed.emit)
        self.addWidget(self.search_edit)

    def set_search_placeholder(self, text: str) -> None:
        self.search_edit.setPlaceholderText(text)

    def search_text(self) -> str:
        return self.search_edit.text().strip()

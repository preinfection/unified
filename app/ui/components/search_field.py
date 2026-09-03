"""Search.

Search in a mail client is not a toolbar decoration; it is how anyone
finds a message older than the last screenful. So it gets a real
keyboard shortcut, real scope, and real feedback about what it is doing -
but *not* a lot of pixels. A search box the size of a hero banner is not
"first class", it is just large.

What is here:

* Ctrl+F / "/" focus it from anywhere, Esc clears and hands focus back to
  the list, so a search never traps the keyboard.
* Its placeholder states the current scope ("Search this account" vs
  "Search all accounts") - the scope is the thing users get wrong, and a
  placeholder is free real estate for saying it.
* A quiet inline status ("searching the server...", "no matches") sits
  under the field, so a slow provider-side search is visible without a
  modal or a spinner parked over the results.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit, QWidget

from app.ui import theme as t
from app.ui.svg_icon import themed


class SearchField(QLineEdit):
    escaped = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("searchField")
        self.setProperty("shape", "pill")
        self.setProperty("surface", "raised")
        self.setClearButtonEnabled(True)
        self.setPlaceholderText("Search all accounts")
        self.setFont(t.make_font("field_value"))
        self.setMinimumHeight(t.CONTROL_MD)
        self.setAccessibleName("Search mail")
        self._leading = self.addAction(
            themed("search", t.ICON_SM, "quiet"),
            QLineEdit.ActionPosition.LeadingPosition,
        )

    def refresh_icon(self) -> None:
        self._leading.setIcon(themed("search", t.ICON_SM, "quiet"))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self.text():
                self.clear()
            self.escaped.emit()
            event.accept()
            return
        super().keyPressEvent(event)

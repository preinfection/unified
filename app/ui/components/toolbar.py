"""Top action bar: Compose (primary), search, then the two utilities.

Refresh and Console are icon-only with tooltips, matching how native
desktop mail clients (Mail.app, Outlook) treat secondary toolbar actions -
icon+text on every button reads as a web toolbar, not a native one.
Compose keeps its label since it's the one primary action worth spelling
out. All icons are real SVG assets tinted per Qt icon Mode (Normal/
Active/Selected/Disabled), never Unicode glyphs.

THE ORDER AND THE SIZING BOTH CHANGED, and the old bar is worth describing
because it looked deliberate and was not:

    [Compose] | [refresh] [console] <--- 400px of nothing ---> [search 340]

Search was a fixed 340px pinned to the right edge, which left a third of
the window's width empty in the middle of the app's only horizontal band,
and put the field that filters the message list as far from that list as
the geometry allowed. The two icon utilities sat immediately beside the
primary action, so the three most different things on the bar were the
three closest together.

Now: primary on the left, search EXPANDING through the middle so the bar
has no dead space at any window width, utilities parked on the right where
secondary controls belong. Nothing is fixed-width except the buttons.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QLineEdit, QPushButton, QSizePolicy, QToolBar, QWidget

from app.ui import theme as t
from app.ui.components.primitives import Button, Variant
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
    btn.setFixedSize(t.HEIGHT_MD, t.HEIGHT_MD)
    return btn


class TopToolBar(QToolBar):
    compose_clicked = Signal()
    refresh_clicked = Signal()
    console_toggled = Signal(bool)
    search_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(False)

        self.compose_btn = Button(" Compose", Variant.PRIMARY)
        self.compose_btn.setIcon(simple_icon("compose", 16, t.TEXT_ON_ACCENT))
        self.compose_btn.setIconSize(QSize(16, 16))
        self.compose_btn.clicked.connect(self.compose_clicked.emit)
        self.addWidget(self.compose_btn)

        gap = QWidget()
        gap.setFixedWidth(t.SPACE_LG)
        self.addWidget(gap)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText("Search all accounts...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(220)
        self.search_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.search_edit.setMinimumHeight(t.HEIGHT_MD - 4)
        self.search_edit.addAction(
            simple_icon("search", 15, t.TEXT_TERTIARY), QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search_edit.textChanged.connect(self.search_changed.emit)
        self.addWidget(self.search_edit)

        gap2 = QWidget()
        gap2.setFixedWidth(t.SPACE_LG)
        self.addWidget(gap2)

        refresh_btn = _icon_button("refresh", "Refresh (sync all accounts)")
        refresh_btn.clicked.connect(self.refresh_clicked.emit)
        self.addWidget(refresh_btn)

        self.console_btn = _icon_button("console", "Show/hide developer console",
                                        checkable=True)
        self.console_btn.toggled.connect(self.console_toggled.emit)
        self.addWidget(self.console_btn)

    def set_compose_enabled(self, enabled: bool) -> None:
        """Compose is only an offer once there is an account to send from.

        It used to stay lit with zero accounts and answer a click with a
        modal telling the user off. A disabled control that explains itself
        on hover is the honest version of that: the interface stops
        promising something it cannot do, and nobody has to dismiss a box
        to find out.
        """
        self.compose_btn.setEnabled(enabled)
        self.compose_btn.setToolTip(
            "" if enabled else "Add an account before writing a message"
        )

    def set_search_placeholder(self, text: str) -> None:
        self.search_edit.setPlaceholderText(text)

    def search_text(self) -> str:
        return self.search_edit.text().strip()

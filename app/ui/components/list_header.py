"""The message list's own header.

The pre-redesign list started at the first row with nothing above it, so
"which mailbox am I in, filtered to what, showing how many" had to be
inferred from whichever thing in the sidebar happened to look selected.
This bar answers all three in one line, at the top of the pane the
question is actually about:

    Inbox · 1,284 messages, 37 unread          [Unread] [⇅] [⋯]

* The scope line names the mailbox *and* the account filter when one is
  applied ("Inbox — work@example.com"), so a filtered view can never be
  mistaken for the whole mailbox.
* An "Unread" toggle, because "show me only what I haven't read" is the
  single most common thing to want from an inbox and it had no UI at all.
* Sort and overflow live here rather than in the global command bar:
  they act on this list, and controls belong next to what they change.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

from app.ui import theme as t
from app.ui.components.buttons import Button, IconButton
from app.ui.svg_icon import themed


class ListHeader(QWidget):
    unread_filter_toggled = Signal(bool)
    select_all_read_requested = Signal()
    density_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("listHeader")
        self.setFixedHeight(t.LIST_HEADER_HEIGHT + t.SPACE_MD)

        row = QHBoxLayout(self)
        row.setContentsMargins(t.SPACE_LG, t.SPACE_SM, t.SPACE_MD, t.SPACE_SM)
        row.setSpacing(t.SPACE_MD)

        column = QVBoxLayout()
        column.setSpacing(0)
        self._title = QLabel("Inbox")
        self._title.setFont(t.make_font("subheading"))
        column.addWidget(self._title)

        self._subtitle = QLabel("")
        self._subtitle.setProperty("tone", "tertiary")
        self._subtitle.setFont(t.make_font("caption"))
        column.addWidget(self._subtitle)
        row.addLayout(column, stretch=1)

        self.unread_button = Button(
            "Unread", variant="subtle", size="sm",
            tooltip="Show only unread messages (U)",
        )
        self.unread_button.setCheckable(True)
        self.unread_button.toggled.connect(self.unread_filter_toggled.emit)
        row.addWidget(self.unread_button)

        self.more_button = IconButton("more_horizontal", "List options", size="sm")
        self.more_button.clicked.connect(self._show_menu)
        row.addWidget(self.more_button)

    def set_scope(self, title: str, account_email: str | None = None) -> None:
        self._title.setText(title if not account_email else f"{title}")
        self._account = account_email
        self._refresh_title(title, account_email)

    def _refresh_title(self, title: str, account_email: str | None) -> None:
        if account_email:
            self._title.setText(f"{title}  ·  {account_email}")
            self._title.setToolTip(f"{title}, filtered to {account_email}")
        else:
            self._title.setText(title)
            self._title.setToolTip("")

    def set_counts(self, shown: int, total: int, unread: int) -> None:
        """State the real numbers. "Showing 100 of 8,412" is the honest
        description of a paged list, and hiding it is how a user concludes
        the app lost their mail."""
        if total == 0:
            text = "No messages"
        elif shown < total:
            text = f"Showing {shown:,} of {total:,}"
        else:
            text = f"{total:,} message{'s' if total != 1 else ''}"
        if unread:
            text += f"  ·  {unread:,} unread"
        self._subtitle.setText(text)

    def set_unread_only(self, enabled: bool) -> None:
        if self.unread_button.isChecked() != enabled:
            self.unread_button.blockSignals(True)
            self.unread_button.setChecked(enabled)
            self.unread_button.blockSignals(False)

    def refresh_icons(self) -> None:
        self.more_button.refresh_icon()

    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(
            themed("mail_open", t.ICON_SM, "default"), "Mark all as read",
            self.select_all_read_requested.emit,
        )
        menu.addSeparator()
        density_menu = menu.addMenu("Density")
        density_menu.setIcon(themed("density", t.ICON_SM, "default"))
        current = t.theme_manager.density
        for value in t.DENSITY_ORDER:
            action = density_menu.addAction(value.capitalize())
            action.setCheckable(True)
            action.setChecked(value == current)
            action.triggered.connect(
                lambda _=False, v=value: self.density_requested.emit(v)
            )
        menu.exec(self.more_button.mapToGlobal(
            self.more_button.rect().bottomLeft()
        ))

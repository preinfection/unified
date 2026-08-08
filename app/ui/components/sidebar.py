"""The account drawer: folder navigation pills, then a scrollable list of
connected accounts with live status, then Add account / Settings.

Rebuilding the account list (set_accounts) is only done when the account
set actually changes (added/removed) - routine sync progress updates go
through the much cheaper update_account_status(), which touches exactly
one existing AccountItem instead of rebuilding the drawer. This matters
because progress ticks can arrive several times a second while syncing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.components.account_item import AccountItem

VIEW_ITEMS = [
    ("inbox", "Unified Inbox"),
    ("starred", "Starred"),
    ("sent", "Sent"),
    ("trash", "Trash"),
]


class SidebarWidget(QWidget):
    view_selected = Signal(str)
    account_selected = Signal(int)
    add_account_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(248)

        self._account_items: dict[int, AccountItem] = {}
        self._current_view: str | None = "inbox"
        self._current_account_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 14, 10, 12)
        root.setSpacing(4)

        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for view, label in VIEW_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("navPill")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.clicked.connect(lambda _=False, v=view: self._on_nav_clicked(v))
            self._nav_group.addButton(btn)
            self._nav_buttons[view] = btn
            root.addWidget(btn)

        root.addSpacing(14)
        section = QLabel("ACCOUNTS")
        section.setObjectName("sectionLabel")
        root.addWidget(section)
        root.addSpacing(2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._accounts_container = QWidget()
        self._accounts_layout = QVBoxLayout(self._accounts_container)
        self._accounts_layout.setContentsMargins(0, 0, 0, 0)
        self._accounts_layout.setSpacing(2)
        self._accounts_layout.addStretch(1)
        scroll.setWidget(self._accounts_container)
        scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        root.addWidget(scroll, stretch=1)

        add_btn = QPushButton("+  Add account...")
        add_btn.setObjectName("navPill")
        add_btn.setFlat(True)
        add_btn.clicked.connect(self.add_account_requested.emit)
        root.addWidget(add_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("navPill")
        settings_btn.setFlat(True)
        settings_btn.clicked.connect(self.settings_requested.emit)
        root.addWidget(settings_btn)

        self._nav_buttons["inbox"].setChecked(True)

    # ------------------------------------------------------------------ nav

    def _on_nav_clicked(self, view: str) -> None:
        self._current_view = view
        self._current_account_id = None
        for item in self._account_items.values():
            item.set_selected(False)
        self.view_selected.emit(view)

    def set_inbox_count(self, total_unread: int) -> None:
        label = "Unified Inbox"
        if total_unread:
            label += f"  ({total_unread})"
        self._nav_buttons["inbox"].setText(label)

    # -------------------------------------------------------------- accounts

    def set_accounts(self, accounts: list[dict], per_account_unread: dict) -> None:
        """Full rebuild - call only when the account set itself changed."""
        for item in self._account_items.values():
            item.setParent(None)
            item.deleteLater()
        self._account_items.clear()

        for account in accounts:
            item = AccountItem(account)
            item.clicked.connect(self._on_account_clicked)
            item.set_unread(per_account_unread.get(account["id"], 0))
            item.set_selected(account["id"] == self._current_account_id)
            self._accounts_layout.insertWidget(
                self._accounts_layout.count() - 1, item
            )
            self._account_items[account["id"]] = item

    def update_account_status(self, account_id: int, status_key: str, text: str) -> None:
        item = self._account_items.get(account_id)
        if item is not None:
            item.set_status(status_key, text)

    def update_unread_counts(self, per_account_unread: dict) -> None:
        for account_id, item in self._account_items.items():
            item.set_unread(per_account_unread.get(account_id, 0))

    def _on_account_clicked(self, account_id: int) -> None:
        self._current_view = None
        self._current_account_id = account_id
        for aid, item in self._account_items.items():
            item.set_selected(aid == account_id)
        for btn in self._nav_buttons.values():
            btn.setAutoExclusive(False)
            btn.setChecked(False)
            btn.setAutoExclusive(True)
        self.account_selected.emit(account_id)

    # -------------------------------------------------------------- external

    def set_current(self, view: str | None, account_id: int | None) -> None:
        """Sync visual selection state without emitting signals - used when
        MainWindow drives the selection (e.g. jumping to a newly added
        account) rather than the user clicking here."""
        self._current_view = view
        self._current_account_id = account_id
        if view is not None and view in self._nav_buttons:
            self._nav_buttons[view].setChecked(True)
        else:
            for btn in self._nav_buttons.values():
                btn.setAutoExclusive(False)
                btn.setChecked(False)
                btn.setAutoExclusive(True)
        for aid, item in self._account_items.items():
            item.set_selected(aid == account_id)

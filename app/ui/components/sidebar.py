"""The navigation column.

Its whole job is answering "where am I, and where else can I go" without
being read. So it is organised as two clearly different kinds of thing,
never mixed:

* **Mailboxes** - the four views (Unified Inbox, Starred, Sent, Trash).
  These are places.
* **Accounts** - the connected addresses. These are *filters* on the
  place you are in.

The pre-redesign sidebar let a folder and an account both look like a
selected pill, which made "Inbox, filtered to this account" and "the
account's inbox" visually identical states, and left no way to tell which
one you were in. Now exactly one of the two groups can be active at a
time and the active one is marked with an accent bar, while a scope line
under the header states the current combination in words.

At narrow window widths the whole column collapses to a 56px icon rail -
labels and the account list drop out, the icons and their tooltips stay,
and the reading pane gets the width instead. That is handled by
`set_collapsed`, which the shell calls from its resize handler.

Rebuilding the account list (`set_accounts`) happens only when the set of
accounts actually changes. Routine sync progress goes through
`update_account_status`, which touches one existing row - progress ticks
arrive several times a second, and rebuilding the drawer on each one is
real UI-thread work during exactly the window the app most needs to stay
responsive.
"""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme as t
from app.ui.components.account_item import AccountItem
from app.ui.components.buttons import Button, IconButton
from app.ui.components.nav_pill import NavList, NavPill
from app.ui.components.section_header import SectionHeader
from app.ui.design import motion

VIEW_ITEMS = [
    ("inbox", "Inbox", "inbox"),
    ("starred", "Starred", "star_outline"),
    ("sent", "Sent", "sent"),
    ("trash", "Trash", "trash"),
]


class SidebarWidget(QWidget):
    view_selected = Signal(str)
    account_selected = Signal(int)
    add_account_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(t.SIDEBAR_WIDTH)
        self.setAccessibleName("Mailbox navigation")

        self._account_items: dict[int, AccountItem] = {}
        self._current_view: str | None = "inbox"
        self._current_account_id: int | None = None
        self._collapsed = False
        self._width_anim = QPropertyAnimation(self, b"maximumWidth", self)
        self._width_anim.setEasingCurve(motion.EASE_SMOOTH_OUT)
        self._min_anim = QPropertyAnimation(self, b"minimumWidth", self)
        self._min_anim.setEasingCurve(motion.EASE_SMOOTH_OUT)

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_MD, t.SPACE_LG, t.SPACE_MD, t.SPACE_MD)
        root.setSpacing(t.SPACE_2XS)

        # -- mailboxes
        self._mailbox_header = SectionHeader("Mailboxes")
        root.addWidget(self._mailbox_header)
        root.addSpacing(t.SPACE_XS)

        # One list, one indicator that travels between rows - see
        # components/nav_pill.py for why selection is not drawn per row.
        self._nav_buttons: dict[str, NavPill] = {}
        self._nav_order: list[str] = []
        self._nav_list = NavList()
        for view, label, icon_name in VIEW_ITEMS:
            button = NavPill(label, icon=icon_name)
            button.setFixedHeight(t.TAB_HEIGHT + t.SPACE_SM)
            button.setToolTip(label)
            self._nav_list.add_item(button)
            self._nav_buttons[view] = button
            self._nav_order.append(view)
        self._nav_list.selected.connect(
            lambda index: self._on_nav_clicked(self._nav_order[index])
        )
        root.addWidget(self._nav_list)

        root.addSpacing(t.SPACE_XL)

        # -- accounts
        self._add_button = IconButton(
            "add_circle", "Add an email account", size="sm"
        )
        self._add_button.clicked.connect(self.add_account_requested.emit)
        self._accounts_header = SectionHeader("Accounts", action=self._add_button)
        root.addWidget(self._accounts_header)
        root.addSpacing(t.SPACE_XS)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        container = QWidget()
        self._accounts_layout = QVBoxLayout(container)
        self._accounts_layout.setContentsMargins(0, 0, 0, 0)
        self._accounts_layout.setSpacing(t.SPACE_2XS)
        self._accounts_layout.addStretch(1)
        self._scroll.setWidget(container)
        self._scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self._scroll, stretch=1)

        # When the account list is hidden (icon rail), something still has
        # to absorb the leftover height - otherwise the layout hands it to
        # the navigation rows and they drift apart down the column.
        self._rail_spacer = QWidget()
        self._rail_spacer.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self._rail_spacer.setVisible(False)
        root.addWidget(self._rail_spacer, stretch=1)

        # -- footer
        self._settings_button = Button(
            "Settings", variant="subtle", icon="settings", size="sm",
            tooltip="Settings (Ctrl+,)",
        )
        self._settings_button.setObjectName("navItem")
        self._settings_button.setFixedHeight(t.TAB_HEIGHT + t.SPACE_SM)
        self._settings_button.clicked.connect(self.settings_requested.emit)
        root.addWidget(self._settings_button)

        self._nav_list.set_current(0, animate=False, emit=False)

    # ------------------------------------------------------------ collapse

    def set_collapsed(self, collapsed: bool) -> None:
        """Icon rail at narrow widths: the reading pane needs the space
        more than the account list does."""
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        target = t.SIDEBAR_RAIL_WIDTH if collapsed else t.SIDEBAR_WIDTH
        duration = t.duration(motion.CARD_RESIZE)
        if duration <= 0:
            self.setFixedWidth(target)
        else:
            # Both bounds travel together, or the layout snaps to one of
            # them and the animation is invisible.
            for animation in (self._width_anim, self._min_anim):
                animation.stop()
                animation.setDuration(duration)
                animation.setStartValue(self.width())
                animation.setEndValue(target)
                animation.start()
        self._mailbox_header.setVisible(not collapsed)
        self._accounts_header.setVisible(not collapsed)
        self._scroll.setVisible(not collapsed)
        self._rail_spacer.setVisible(collapsed)
        self._nav_list.set_collapsed(collapsed)
        self._settings_button.setText("" if collapsed else "Settings")
        self._settings_button.setProperty("shape", "icon" if collapsed else None)
        t.repolish(self._settings_button)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def refresh_icons(self) -> None:
        for button in self._nav_buttons.values():
            button.refresh_icon()
        self._add_button.refresh_icon()
        self._settings_button.refresh_icon()

    # ----------------------------------------------------------------- nav

    def _on_nav_clicked(self, view: str) -> None:
        self._current_view = view
        self._current_account_id = None
        for item in self._account_items.values():
            item.set_selected(False)
        self.view_selected.emit(view)

    def set_inbox_count(self, total_unread: int) -> None:
        self._nav_buttons["inbox"].set_count(total_unread)

    def set_view_counts(self, counts: dict[str, int]) -> None:
        for view, count in counts.items():
            button = self._nav_buttons.get(view)
            if button is not None:
                button.set_count(count)

    # ------------------------------------------------------------ accounts

    def set_accounts(self, accounts: list[dict], per_account_unread: dict) -> None:
        """Full rebuild - only when the account set itself changed."""
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
        self._current_account_id = account_id
        for aid, item in self._account_items.items():
            item.set_selected(aid == account_id)
        # An account is a filter on the current mailbox, not a place of
        # its own, so the mailbox stays selected while it is applied.
        self.account_selected.emit(account_id)

    # -------------------------------------------------------------- external

    def set_current(self, view: str | None, account_id: int | None) -> None:
        """Reflect a selection driven by the shell (e.g. jumping to a
        newly added account) without emitting signals back at it."""
        self._current_view = view
        self._current_account_id = account_id
        if view is not None and view in self._nav_order:
            self._nav_list.set_current(
                self._nav_order.index(view), emit=False
            )
        else:
            self._nav_list.clear_current()
        for aid, item in self._account_items.items():
            item.set_selected(aid == account_id)

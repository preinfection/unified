"""The account drawer: the masthead, then whose mail is showing.

WHAT MOVED OUT. Folder navigation (Inbox, Starred, Sent, Trash), "Add
account" and Settings now live in the dock at the top of the window. The
drawer used to answer two questions in one list - which folder, and which
account - and the two answers had to take turns: selecting an account
un-selected the folder, so the drawer could never show both. Now the dock
says WHERE and this says WHOSE, and each can be true at once.

What is left is small on purpose: the wordmark and the product's one
standing claim, the "Accounts" heading, and one row per account with
"All accounts" first. Exactly one row is selected, always.

"ADD ACCOUNT" IS NOT REPEATED HERE. It used to sit under the account rows.
With the dock carrying it permanently and the empty state offering it as
the primary action on a first run, a third copy in the drawer made three
competing offers on the first screen anyone sees.

Rebuilding the account list (set_accounts) happens only when the account
set actually changes; routine sync progress goes through the much cheaper
update_account_status(), which touches exactly one existing AccountItem
instead of rebuilding the drawer. That matters because progress ticks
arrive several times a second while syncing.

=========================================================================
IT COLLAPSES TO A RAIL, and the reason is width rather than fashion. The
drawer is a fixed 248px, which is a quarter of a 1000px window - and this
is a three-pane application, so that quarter comes straight out of the
message list and the reading pane, the two surfaces the product exists
for. Collapsed, every row keeps its avatar, its tooltip, its accessible
name and its keyboard reachability; what goes is the text.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME
from app.ui import motion, theme as t
from app.ui.components.account_item import ALL_ACCOUNTS, AccountItem
from app.ui.components.primitives import IconButton
from app.ui.components.section_header import SectionHeader
from app.ui.svg_icon import simple_icon

# Wide enough for a 30px avatar with air on both sides, narrow enough to be
# worth collapsing to.
RAIL_WIDTH = 56


class SidebarWidget(QWidget):
    #: An account id, or ALL_ACCOUNTS (None) for every account at once.
    scope_selected = Signal(object)
    collapsed_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(t.SIDEBAR_WIDTH)
        # A bare QWidget subclass needs this for its QSS background.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._account_items: dict[int, AccountItem] = {}
        self._current_scope: int | None = ALL_ACCOUNTS
        self._collapsed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_SM, t.SPACE_MD, t.SPACE_SM, t.SPACE_MD)
        root.setSpacing(t.SPACE_XXS)
        self._root = root

        root.addWidget(self._build_masthead())
        root.addSpacing(t.SPACE_XL)

        self._accounts_header = SectionHeader("Accounts")
        root.addWidget(self._accounts_header)
        root.addSpacing(t.SPACE_XS)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # The rows take focus; the container around them must not, or Tab
        # stops once on something with no visible focus at all.
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._accounts_container = QWidget()
        self._accounts_layout = QVBoxLayout(self._accounts_container)
        self._accounts_layout.setContentsMargins(0, 0, 0, 0)
        self._accounts_layout.setSpacing(2)

        # "All accounts" leads the list and exists only once there is an
        # account for it to mean.
        self._all_item = AccountItem(None)
        self._all_item.clicked.connect(self._on_row_clicked)
        self._all_item.set_selected(True)
        self._all_item.setVisible(False)
        self._accounts_layout.addWidget(self._all_item)

        # With nothing connected the heading would otherwise sit over an
        # empty region that reads as a list that failed to load.
        self._empty_note = QLabel("None connected yet")
        self._empty_note.setFont(t.make_font("caption"))
        t.role(self._empty_note, "tertiary")
        self._empty_note.setContentsMargins(t.SPACE_XS, t.SPACE_XS, 0, 0)
        self._accounts_layout.addWidget(self._empty_note)
        self._accounts_layout.addStretch(1)

        scroll.setWidget(self._accounts_container)
        scroll.setSizePolicy(QSizePolicy.Policy.Preferred,
                             QSizePolicy.Policy.Expanding)
        root.addWidget(scroll, stretch=1)

    # --------------------------------------------------------------- pieces

    def _build_masthead(self) -> QWidget:
        """App identity, a quiet "your mail is encrypted locally" cue, and
        the collapse control.

        THE LOCK BELONGS TO THE SENTENCE. It sits directly before the
        caption, at caption size, so the row reads as one statement: lock,
        "Encrypted locally".
        """
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(t.SPACE_XS + 2, t.SPACE_SM, 0, t.SPACE_XS)
        row.setSpacing(0)

        self._title_col = QWidget()
        title_col = QVBoxLayout(self._title_col)
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(t.SPACE_XS)

        name = QLabel(APP_NAME)
        name.setFont(t.make_font("app_title"))
        t.role(name, "primary")
        title_col.addWidget(name)

        secure_row = QHBoxLayout()
        secure_row.setContentsMargins(0, 0, 0, 0)
        secure_row.setSpacing(t.SPACE_XS + 2)

        self._lock = QLabel()
        self._lock.setPixmap(simple_icon("lock", 12, t.SECURE).pixmap(12, 12))
        secure_row.addWidget(self._lock, 0, Qt.AlignmentFlag.AlignVCenter)

        caption = QLabel("Encrypted locally")
        caption.setFont(t.make_font("caption"))
        t.role(caption, "tertiary")
        secure_row.addWidget(caption, 0, Qt.AlignmentFlag.AlignVCenter)
        secure_row.addStretch(1)

        holder = QWidget()
        holder.setLayout(secure_row)
        holder.setToolTip(
            "The local mailbox cache is encrypted at rest (AES-256-GCM). "
            "This protects the copy on this machine, not the mail at your "
            "provider."
        )
        title_col.addWidget(holder)
        row.addWidget(self._title_col)
        row.addStretch(1)

        self.collapse_btn = IconButton(
            "panel_left", "Collapse the sidebar", size=t.ICON_SIZE_NAV
        )
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        row.addWidget(self.collapse_btn, 0, Qt.AlignmentFlag.AlignTop)

        # A SECOND STRETCH, NORMALLY INERT. Expanded, the control belongs
        # hard right, opposite the wordmark. Collapsed, the wordmark is gone
        # and a single leading stretch would pin the control to the rail's
        # right edge - a few pixels off the vertical line every avatar below
        # it sits on. Giving this weight too centres it between them.
        row.addStretch(0)
        self._masthead_row = row
        self._trailing_stretch = row.count() - 1
        return bar

    # ------------------------------------------------------------- collapse

    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool, *, animate: bool = True) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed

        # CONTENTS FIRST, WIDTH SECOND. The other order elides every label
        # against a shrinking width for the length of the animation, so the
        # drawer spends 280ms full of half-truncated words on its way to
        # hiding them.
        self._apply_collapsed_contents()

        target = RAIL_WIDTH if collapsed else t.SIDEBAR_WIDTH
        if animate and motion.motion_enabled():
            anim = QPropertyAnimation(self, b"railWidth", self)
            anim.setDuration(t.DURATION_SLOW)
            anim.setEasingCurve(motion.curve())
            anim.setStartValue(float(self.width()))
            anim.setEndValue(float(target))
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        else:
            self.setFixedWidth(target)

        self.collapsed_changed.emit(collapsed)

    def _get_rail_width(self) -> float:
        return float(self.width())

    def _set_rail_width(self, value: float) -> None:
        self.setFixedWidth(int(value))

    # A fixed width can only be animated through a real Qt property;
    # width() is not one.
    railWidth = Property(float, _get_rail_width, _set_rail_width)

    def _apply_collapsed_contents(self) -> None:
        collapsed = self._collapsed

        self._title_col.setVisible(not collapsed)
        self._accounts_header.setVisible(not collapsed)
        self._refresh_empty_note()
        pad = t.SPACE_XS if collapsed else t.SPACE_SM
        self._root.setContentsMargins(pad, t.SPACE_MD, pad, t.SPACE_MD)
        self._masthead_row.setContentsMargins(
            0 if collapsed else t.SPACE_XS + 2, t.SPACE_SM, 0, t.SPACE_XS
        )
        self._masthead_row.setStretch(self._trailing_stretch, 1 if collapsed else 0)

        self.collapse_btn.setToolTip(
            "Expand the sidebar" if collapsed else "Collapse the sidebar"
        )
        self.collapse_btn.setAccessibleName(self.collapse_btn.toolTip())

        for item in self.rows():
            item.set_collapsed(collapsed)

    def retheme(self) -> None:
        """Re-tint the lock; everything else paints from tokens or follows
        the stylesheet."""
        self._lock.setPixmap(simple_icon("lock", 12, t.SECURE).pixmap(12, 12))
        for item in self.rows():
            item.update()

    # -------------------------------------------------------------- accounts

    def rows(self) -> list[AccountItem]:
        """Every scope row in display order, "All accounts" first."""
        return [self._all_item, *self._account_items.values()]

    def set_accounts(self, accounts: list[dict], per_account_unread: dict) -> None:
        """Full rebuild - call only when the account set itself changed."""
        for item in self._account_items.values():
            item.setParent(None)
            item.deleteLater()
        self._account_items.clear()

        # After "All accounts", before the empty note and the stretch.
        insert_at = self._accounts_layout.indexOf(self._all_item) + 1
        for offset, account in enumerate(accounts):
            item = AccountItem(account)
            item.clicked.connect(self._on_row_clicked)
            item.set_unread(per_account_unread.get(account["id"], 0))
            item.set_collapsed(self._collapsed)
            self._accounts_layout.insertWidget(insert_at + offset, item)
            self._account_items[account["id"]] = item

        self._all_item.setVisible(bool(accounts))
        self._all_item.set_collapsed(self._collapsed)
        self._all_item.set_unread(sum(per_account_unread.get(a["id"], 0)
                                      for a in accounts))
        self._refresh_empty_note()
        # A scope whose account was just removed cannot stay selected.
        if self._current_scope not in self._account_items:
            self._current_scope = ALL_ACCOUNTS
        self._paint_selection()

        # Tab order down the list follows the list.
        rows = self.rows()
        for a, b in zip(rows, rows[1:]):
            QWidget.setTabOrder(a, b)

    def _refresh_empty_note(self) -> None:
        self._empty_note.setVisible(not self._account_items and not self._collapsed)

    def update_account_status(self, account_id: int, status_key: str,
                              text: str) -> None:
        item = self._account_items.get(account_id)
        if item is not None:
            item.set_status(status_key, text)

    def update_unread_counts(self, per_account_unread: dict) -> None:
        for account_id, item in self._account_items.items():
            item.set_unread(per_account_unread.get(account_id, 0))
        self._all_item.set_unread(sum(
            per_account_unread.get(aid, 0) for aid in self._account_items
        ))

    def _on_row_clicked(self, scope) -> None:
        # A request, not a decision: MainWindow owns what is current and
        # tells the drawer back through set_current_scope. Painting the
        # choice here first as well would make two owners of one state -
        # the exact arrangement that let the old drawer show two
        # selections at once.
        self.scope_selected.emit(scope)

    # -------------------------------------------------------------- external

    def set_current_scope(self, account_id: int | None) -> None:
        """Show which scope is current. Never emits."""
        if account_id is not ALL_ACCOUNTS and account_id not in self._account_items:
            account_id = ALL_ACCOUNTS
        self._current_scope = account_id
        self._paint_selection()

    def current_scope(self) -> int | None:
        return self._current_scope

    def _paint_selection(self) -> None:
        for item in self.rows():
            item.set_selected(item.account_id == self._current_scope)

    def selected_rows(self) -> list[AccountItem]:
        return [item for item in self.rows() if item.is_selected()]

    def focus_row_step(self, row: AccountItem, step: int) -> None:
        """Up and Down move along the account rows when one has focus."""
        rows = [r for r in self.rows() if r.isVisible()]
        if row not in rows:
            return
        index = max(0, min(len(rows) - 1, rows.index(row) + step))
        rows[index].setFocus(Qt.FocusReason.TabFocusReason)

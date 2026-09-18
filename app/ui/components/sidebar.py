"""The account drawer: app masthead, folder navigation, then the connected
accounts with live status, then Settings.

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
for. On a laptop the standing trade is between reading a message and
seeing which folder you are in, permanently, in favour of the folder.

Collapsed, every destination keeps its icon, its tooltip, its accessible
name and its keyboard reachability; what goes is the text. The transition
is animated because the panes either side are resizing at the same moment,
and a pane that jumps to a new width is harder to follow than one that
travels there.

=========================================================================
"ADD ACCOUNT" MOVED, AND THAT WAS A GROUPING BUG. It used to be pinned to
the very bottom beside Settings, which put the action that adds to the
account list a few hundred pixels below the account list, with an empty
region between them - on a three-account sidebar, 330px of nothing. Two
unrelated things were adjacent (add an account, change settings) and two
related things were not. It now sits directly under the accounts it adds
to, inside the same scroll region, so the group reads as one thing.
Settings stays pinned at the bottom, where a utility action belongs and
where it is not pretending to be part of anything.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property, QPropertyAnimation, QRectF, QSize, Qt, Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME
from app.ui import motion, theme as t
from app.ui.components.account_item import AccountItem
from app.ui.components.nav_pill import NavPill
from app.ui.components.primitives import IconButton
from app.ui.components.section_header import SectionHeader
from app.ui.svg_icon import icon_set, simple_icon

VIEW_ITEMS = [
    ("inbox", "Unified Inbox", "inbox"),
    ("starred", "Starred", "starred_nav"),
    ("sent", "Sent", "sent"),
    ("trash", "Trash", "trash"),
]

# Wide enough for a 17px glyph centred in a 34px pill with air on both
# sides, narrow enough to be worth collapsing to.
RAIL_WIDTH = 56


def _nav_icon(name: str):
    return icon_set(
        name, t.ICON_SIZE_NAV,
        normal=t.ICON_SECONDARY, active=t.ICON_ACTIVE, selected=t.ICON_SELECTED,
    )


class SidebarWidget(QWidget):
    view_selected = Signal(str)
    account_selected = Signal(int)
    add_account_requested = Signal()
    settings_requested = Signal()
    collapsed_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(t.SIDEBAR_WIDTH)

        self._account_items: dict[int, AccountItem] = {}
        self._current_view: str | None = "inbox"
        self._current_account_id: int | None = None
        self._collapsed = False
        self._inbox_unread = 0
        self._nav_labels: dict[str, str] = {}
        # The shared selection surface: one rounded rect that travels
        # between destinations instead of each pill fading its own.
        self._indicator = QRectF()
        self._indicator_opacity = 0.0
        self._indicator_anim: QPropertyAnimation | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_SM, t.SPACE_MD, t.SPACE_SM, t.SPACE_MD)
        root.setSpacing(t.SPACE_XXS)
        self._root = root

        root.addWidget(self._build_masthead())
        root.addSpacing(t.SPACE_LG)

        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for view, label, icon_name in VIEW_ITEMS:
            btn = NavPill(f"  {label}")
            btn.setFont(t.make_font("nav_label"))
            btn.setIcon(_nav_icon(icon_name))
            btn.setIconSize(QSize(t.ICON_SIZE_NAV, t.ICON_SIZE_NAV))
            btn.setProperty("iconName", icon_name)
            btn.clicked.connect(lambda _=False, v=view: self._on_nav_clicked(v))
            self._nav_group.addButton(btn)
            self._nav_buttons[view] = btn
            self._nav_labels[view] = label
            root.addWidget(btn)

        root.addSpacing(t.SPACE_LG)
        self._accounts_header = SectionHeader("Accounts")
        root.addWidget(self._accounts_header)
        root.addSpacing(t.SPACE_XXS)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._accounts_container = QWidget()
        self._accounts_layout = QVBoxLayout(self._accounts_container)
        self._accounts_layout.setContentsMargins(0, 0, 0, 0)
        self._accounts_layout.setSpacing(2)

        # Inside the scroll region and directly beneath the account rows,
        # so it follows the list however long the list gets.
        self._add_btn = self._make_nav_button("add_circle", "Add account...")
        self._add_btn.clicked.connect(self.add_account_requested.emit)
        self._accounts_layout.addWidget(self._add_btn)
        self._accounts_layout.addStretch(1)

        scroll.setWidget(self._accounts_container)
        scroll.setSizePolicy(QSizePolicy.Policy.Preferred,
                             QSizePolicy.Policy.Expanding)
        root.addWidget(scroll, stretch=1)

        self._settings_btn = self._make_nav_button("settings", "Settings")
        self._settings_btn.clicked.connect(self.settings_requested.emit)
        root.addWidget(self._settings_btn)

        self._nav_buttons["inbox"].setChecked(True)

    # --------------------------------------------------------------- pieces

    def _make_nav_button(self, icon_name: str, label: str) -> QPushButton:
        btn = QPushButton(f"  {label}")
        btn.setObjectName("navPill")
        btn.setFont(t.make_font("nav_label"))
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIcon(_nav_icon(icon_name))
        btn.setIconSize(QSize(t.ICON_SIZE_NAV, t.ICON_SIZE_NAV))
        btn.setProperty("fullLabel", label)
        btn.setProperty("iconName", icon_name)
        btn.setAccessibleName(label)
        return btn

    def _build_masthead(self) -> QWidget:
        """App identity, a quiet "your mail is encrypted locally" cue, and
        the collapse control.

        THE LOCK BELONGS TO THE SENTENCE. It used to be pushed to the far
        right of the masthead by a stretch, level with the wordmark, a full
        sidebar-width from the words "Encrypted locally" that it
        illustrates - two unrelated objects sharing a line. It sits
        directly before the caption now, at caption size, so the row reads
        as one statement: lock, "Encrypted locally".
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
        # hard right, opposite the wordmark, so this carries no weight.
        # Collapsed, the wordmark is gone and a single leading stretch
        # would pin the control to the rail's right edge - a few pixels off
        # the vertical line every nav glyph and avatar below it sits on,
        # which is the kind of misalignment that reads as sloppy without
        # being nameable. Giving this weight too centres it between them.
        row.addStretch(0)
        self._masthead_row = row
        self._trailing_stretch = row.count() - 1
        return bar

    # ------------------------------------------------------------ indicator

    def _get_indicator_rect(self) -> QRectF:
        return self._indicator

    def _set_indicator_rect(self, rect: QRectF) -> None:
        self._indicator = rect
        self.update()

    indicatorRect = Property(QRectF, _get_indicator_rect, _set_indicator_rect)

    def _get_indicator_opacity(self) -> float:
        return self._indicator_opacity

    def _set_indicator_opacity(self, value: float) -> None:
        self._indicator_opacity = float(value)
        self.update()

    indicatorOpacity = Property(
        float, _get_indicator_opacity, _set_indicator_opacity
    )

    def _selected_pill(self):
        for button in self._nav_buttons.values():
            if button.isChecked():
                return button
        return None

    def _move_indicator(self, *, animate: bool = True) -> None:
        """Send the selection surface to whichever destination is current.

        ADAPTED FROM MAGIC UI'S DOCK, and specifically NOT its
        magnification. What makes that component feel alive is that the
        whole dock responds as ONE object - every icon's size is derived
        continuously from a single mouseX rather than each one toggling
        its own hover state. Resizing icons would be wrong here (a
        vertical nav would reflow, and a mail client is not a launcher),
        but the "one object, one response" half transfers exactly.

        Before this, each pill tweened its own fill, so moving from Inbox
        to Sent was a cross-dissolve: the old one at 50% and the new one
        at 50% simultaneously for 180ms, which reads as two things
        half-happening rather than one thing moving. One rect that
        travels is unambiguous, and it is also cheaper - one animation
        instead of two.
        """
        target = self._selected_pill()
        if target is None:
            # An account is selected instead, so no folder is. The surface
            # fades out where it stands rather than jumping to a corner.
            if self._indicator_opacity:
                motion.animate_property(
                    self, "indicatorOpacity", 0.0, duration=t.DURATION_FAST
                )
            return

        rect = QRectF(target.geometry())
        if self._indicator.isNull() or not animate or not motion.motion_enabled():
            self._set_indicator_rect(rect)
            self._set_indicator_opacity(1.0)
            return

        if self._indicator_anim is not None:
            self._indicator_anim.stop()
        anim = QPropertyAnimation(self, b"indicatorRect", self)
        anim.setDuration(t.DURATION_BASE)
        anim.setEasingCurve(motion.curve())
        anim.setStartValue(self._indicator)
        anim.setEndValue(rect)
        anim.start(QPropertyAnimation.DeletionPolicy.KeepWhenStopped)
        self._indicator_anim = anim
        if self._indicator_opacity < 1.0:
            motion.animate_property(self, "indicatorOpacity", 1.0)

    def paintEvent(self, event) -> None:  # noqa: N802
        """The selection surface, painted behind every child.

        The pills are transparent, so a rect drawn by the parent shows
        through underneath their icon and label - which is what lets one
        surface serve all of them.
        """
        super().paintEvent(event)
        if self._indicator.isNull() or self._indicator_opacity <= 0.001:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        fill = QColor(t.BG_SELECTED)
        fill.setAlphaF(min(1.0, self._indicator_opacity))
        painter.setBrush(fill)
        painter.drawRoundedRect(
            self._indicator.adjusted(0.5, 0.5, -0.5, -0.5),
            float(t.RADIUS_MD), float(t.RADIUS_MD),
        )
        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Geometry changed under it (collapse, window resize); the surface
        # has to follow without narrating the move.
        self._move_indicator(animate=False)

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

    @staticmethod
    def _set_railed(button: QPushButton, railed: bool) -> None:
        """Flip the QSS property that centres a pill's glyph, and force the
        re-polish Qt will not do on its own for a property selector."""
        button.setProperty("railed", "true" if railed else "")
        style = button.style()
        if style is not None:
            style.unpolish(button)
            style.polish(button)

    def _apply_collapsed_contents(self) -> None:
        collapsed = self._collapsed

        self._title_col.setVisible(not collapsed)
        self._accounts_header.setVisible(not collapsed)
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

        for view, btn in self._nav_buttons.items():
            label = self._nav_labels[view]
            btn.setText("" if collapsed else f"  {label}")
            # A LABEL-LESS CONTROL WITH NO TOOLTIP IS A GUESS, and with no
            # accessible name it is announced as "" out loud.
            btn.setToolTip(label if collapsed else "")
            btn.setAccessibleName(label)
            self._set_railed(btn, collapsed)

        for btn in (self._add_btn, self._settings_btn):
            label = btn.property("fullLabel")
            btn.setText("" if collapsed else f"  {label}")
            btn.setToolTip(label if collapsed else "")
            self._set_railed(btn, collapsed)

        for item in self._account_items.values():
            item.set_collapsed(collapsed)

        # Restate the count in whichever form now fits.
        self.set_inbox_count(self._inbox_unread)
        # The pills just changed width; the surface has to be where they
        # are, and without narrating a move the user did not ask for.
        self._move_indicator(animate=False)

    # ------------------------------------------------------------------ nav

    def _clear_nav_selection(self) -> None:
        """Uncheck every folder, which needs the GROUP to stand down.

        THIS WAS A REAL BUG, and the shared indicator is what exposed it.
        Unchecking the buttons individually - setAutoExclusive(False),
        setChecked(False), setAutoExclusive(True) - does not defeat a
        QButtonGroup, which enforces exclusivity on its own and simply
        re-checks the last member. So selecting an ACCOUNT left "Unified
        Inbox" checked underneath it, and the drawer showed two things
        selected at once: a highlighted folder and a highlighted account.

        It was easy to miss while every pill painted its own fill, because
        a second highlight two hundred pixels up reads as background. One
        travelling surface cannot be in two places, so it had to be fixed.
        """
        self._nav_group.setExclusive(False)
        for btn in self._nav_buttons.values():
            btn.setChecked(False)
        self._nav_group.setExclusive(True)

    def _on_nav_clicked(self, view: str) -> None:
        self._current_view = view
        self._current_account_id = None
        for item in self._account_items.values():
            item.set_selected(False)
        self._move_indicator()
        self.view_selected.emit(view)

    def set_inbox_count(self, total_unread: int) -> None:
        self._inbox_unread = total_unread
        button = self._nav_buttons["inbox"]
        if self._collapsed:
            # There is no room for a count beside a hidden label, so the
            # tooltip carries it rather than the number simply vanishing.
            button.setToolTip(
                f"Unified Inbox ({total_unread})" if total_unread
                else "Unified Inbox"
            )
            return
        label = "  Unified Inbox"
        if total_unread:
            label += f"  ({total_unread})"
        button.setText(label)

    def retheme(self) -> None:
        """Re-tint every icon in the drawer; text follows the stylesheet."""
        for view, btn in self._nav_buttons.items():
            btn.setIcon(_nav_icon(btn.property("iconName")))
        for btn in (self._add_btn, self._settings_btn):
            btn.setIcon(_nav_icon(btn.property("iconName")))
        self._lock.setPixmap(simple_icon("lock", 12, t.SECURE).pixmap(12, 12))

    # -------------------------------------------------------------- accounts

    def set_accounts(self, accounts: list[dict], per_account_unread: dict) -> None:
        """Full rebuild - call only when the account set itself changed."""
        for item in self._account_items.values():
            item.setParent(None)
            item.deleteLater()
        self._account_items.clear()

        # Above "Add account..." and the trailing stretch, so the action
        # stays directly beneath the rows it adds to.
        insert_at = max(0, self._accounts_layout.count() - 2)
        for offset, account in enumerate(accounts):
            item = AccountItem(account)
            item.clicked.connect(self._on_account_clicked)
            item.set_unread(per_account_unread.get(account["id"], 0))
            item.set_selected(account["id"] == self._current_account_id)
            item.set_collapsed(self._collapsed)
            self._accounts_layout.insertWidget(insert_at + offset, item)
            self._account_items[account["id"]] = item

    def update_account_status(self, account_id: int, status_key: str,
                              text: str) -> None:
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
        self._clear_nav_selection()
        self._move_indicator()
        self.account_selected.emit(account_id)

    # -------------------------------------------------------------- external

    def set_current(self, view: str | None, account_id: int | None) -> None:
        """Sync the visual selection without emitting signals - used when
        MainWindow drives the selection (jumping to a newly added account,
        say) rather than the user clicking here."""
        self._current_view = view
        self._current_account_id = account_id
        if view is not None and view in self._nav_buttons:
            self._nav_buttons[view].setChecked(True)
        else:
            self._clear_nav_selection()
        for aid, item in self._account_items.items():
            item.set_selected(aid == account_id)
        self._move_indicator()

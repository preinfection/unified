"""One row in the sidebar's account list: avatar, address, unread badge,
live sync status. A handful of these exist at once (one per connected
account, plus "All accounts"), so plain QWidget children are the right
call here - unlike the email list, there is no virtualization concern at
this scale.

THE ROWS ARE A SCOPE, NOT A FOLDER. Since the folders moved to the dock,
this list answers exactly one question - whose mail is showing - and
"All accounts" is the answer that means everyone's. Exactly one row is
selected at any time, and it is never in competition with the folder,
because the folder is shown somewhere else.

SELECTION IS A PROPERTY, NOT AN INLINE STYLESHEET. The selected surface
used to be written into each row with setStyleSheet(f"...{t.BG_SELECTED}"),
which froze the dark palette's value into the widget: after switching to
the light theme the selected account kept a dark-mode slab behind it until
something else happened to rebuild the row. A dynamic property is
re-evaluated by the application stylesheet on every theme switch.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui import theme as t
from app.ui.components.avatar import paint_avatar
from app.ui.components.primitives import ElidingLabel
from app.ui.components.status_indicator import StatusIndicator
from app.ui.svg_icon import paint_icon

_AVATAR_SIZE = 30
# Every row is the same height whether or not it has a status line, so the
# list keeps one rhythm - "All accounts" has no sync status of its own.
ROW_HEIGHT = 48

#: The key an AccountItem uses for "every account at once".
ALL_ACCOUNTS = None


class _Avatar(QWidget):
    def __init__(self, email: str | None, parent=None):
        super().__init__(parent)
        self.email = email
        self.setFixedSize(_AVATAR_SIZE, _AVATAR_SIZE)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = QRectF(0, 0, _AVATAR_SIZE, _AVATAR_SIZE)
        if self.email is None:
            # "All accounts" is not a person, so it gets a mark rather than
            # an initial: the layered glyph, on the quietest disc.
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t.BG_HOVER))
            painter.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))
            glyph = 16.0
            paint_icon(
                painter, "layers",
                QRectF((_AVATAR_SIZE - glyph) / 2, (_AVATAR_SIZE - glyph) / 2,
                       glyph, glyph),
                t.ICON_SECONDARY,
            )
        else:
            paint_avatar(painter, rect, self.email, "", self.email)
        painter.end()


class AccountItem(QWidget):
    #: The account id, or ALL_ACCOUNTS (None) for the aggregate row.
    clicked = Signal(object)

    def __init__(self, account: dict | None, parent=None):
        super().__init__(parent)
        self.account_id = account["id"] if account else ALL_ACCOUNTS
        self._email = account["email"] if account else "All accounts"
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("accountItem")
        self.setProperty("selected", "false")
        # Required for the QSS :hover pseudo-state to fire on a bare QWidget,
        # and for a QSS background to be painted at all.
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Reachable from the keyboard: Tab lands here, Up/Down move along
        # the list (see SidebarWidget), Enter or Space selects. Tab only -
        # a click must not pull focus out of the message list.
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setMinimumHeight(ROW_HEIGHT)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(t.SPACE_SM, t.SPACE_SM - 1, t.SPACE_SM, t.SPACE_SM - 1)
        outer.setSpacing(t.SPACE_SM)

        self._avatar = _Avatar(account["email"] if account else None)
        outer.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.addStretch(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(t.SPACE_XS + 2)
        # Eliding, because a long address in a 248px drawer otherwise
        # pushes the unread badge out of the row.
        self._email_label = ElidingLabel(self._email)
        self._email_label.setObjectName("accountEmail")
        self._email_label.setFont(t.make_font("account_label"))
        top_row.addWidget(self._email_label, stretch=1)
        self._badge = QLabel("")
        self._badge.setObjectName("unreadBadge")
        self._badge.setVisible(False)
        top_row.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        text_col.addLayout(top_row)

        self._status = StatusIndicator()
        text_col.addWidget(self._status)
        text_col.addStretch(1)

        outer.addLayout(text_col, stretch=1)
        self._outer = outer
        self._collapsed = False
        self._unread = 0
        self._refresh_accessible_name()

    def is_aggregate(self) -> bool:
        return self.account_id is ALL_ACCOUNTS

    def set_collapsed(self, collapsed: bool) -> None:
        """Avatar only, when the drawer is a rail.

        The email, the badge and the status line are HIDDEN rather than
        removed, so expanding again does not have to rebuild the row. The
        avatar stays because it is the one part of an account row still
        legible at 56px, and because it is already how accounts are told
        apart in the message list - the same cue in both places.
        """
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._email_label.setVisible(not collapsed)
        # THE BADGE IS NOT A PLAIN setVisible, for the same reason the
        # status line is not. Forcing it visible on expand showed an EMPTY
        # grey pill beside every account with nothing unread - the widget
        # exists whatever the count is, and only the count decides whether
        # it should be seen. Two owners of one visibility flag again.
        self._refresh_badge()
        # Likewise: the status line decides its own visibility from whether
        # it has text, and sync ticks would otherwise show it again moments
        # after collapsing. See StatusIndicator.set_suppressed.
        self._status.set_suppressed(collapsed)
        pad = 0 if collapsed else t.SPACE_SM
        self._outer.setContentsMargins(
            pad, t.SPACE_SM - 1, pad, t.SPACE_SM - 1
        )
        # The row has lost its label, so it has to say what it is some
        # other way: a rail of anonymous avatars is a guessing game.
        self._refresh_tooltip()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.account_id)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self.account_id)
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            owner = self.parentWidget()
            while owner is not None and not hasattr(owner, "focus_row_step"):
                owner = owner.parentWidget()
            if owner is not None:
                owner.focus_row_step(self, -1 if key == Qt.Key.Key_Up else 1)
                return
        super().keyPressEvent(event)

    _OWN_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space,
                 Qt.Key.Key_Up, Qt.Key.Key_Down)

    def event(self, event) -> bool:
        # Enter and the arrows are bound window-wide to "open / step through
        # the message list". On a focused account row they have to mean
        # this list instead, or the keyboard moves something the user is
        # not looking at.
        if (event.type() == QEvent.Type.ShortcutOverride
                and event.key() in self._OWN_KEYS):
            event.accept()
            return True
        return super().event(event)

    def set_selected(self, selected: bool) -> None:
        if selected == self._selected:
            return
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        # Qt does not re-evaluate a property selector on its own.
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def is_selected(self) -> bool:
        return self._selected

    def set_unread(self, count: int) -> None:
        self._unread = max(0, int(count))
        self._refresh_badge()
        self._refresh_accessible_name()
        self._refresh_tooltip()

    def unread(self) -> int:
        return self._unread

    def _refresh_badge(self) -> None:
        """One place decides whether the count is on screen.

        Both the unread count and the collapsed state have an opinion here,
        so neither is allowed to call setVisible directly - see the note in
        set_collapsed.
        """
        count = self._unread
        # 99+ rather than a four-digit pill that resizes the row it is in.
        self._badge.setText(str(count) if count < 100 else "99+")
        self._badge.setVisible(bool(count) and not self._collapsed)

    def _refresh_accessible_name(self) -> None:
        name = self._email
        if self._unread:
            name += f", {self._unread} unread"
        self.setAccessibleName(name)

    def _refresh_tooltip(self) -> None:
        if not self._collapsed:
            self.setToolTip("")
            return
        tip = self._email
        if self._unread:
            tip += f"  ({self._unread} unread)"
        self.setToolTip(tip)

    def set_status(self, status_key: str, text: str) -> None:
        self._status.set_status(status_key, text)

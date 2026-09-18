"""One account row in the sidebar drawer: avatar, email, unread badge,
live sync status. A handful of these exist at once (one per connected
account), so plain QWidget children are the right call here - unlike the
email list, there is no virtualization concern at this scale.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui import theme as t
from app.ui.components.avatar import paint_avatar
from app.ui.components.status_indicator import StatusIndicator

_AVATAR_SIZE = 30


class _Avatar(QWidget):
    def __init__(self, email: str, parent=None):
        super().__init__(parent)
        self.email = email
        self.setFixedSize(_AVATAR_SIZE, _AVATAR_SIZE)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        paint_avatar(
            painter, QRectF(0, 0, _AVATAR_SIZE, _AVATAR_SIZE),
            self.email, "", self.email,
        )


class AccountItem(QWidget):
    clicked = Signal(int)  # account_id

    def __init__(self, account: dict, parent=None):
        super().__init__(parent)
        self.account_id = account["id"]
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("accountItem")
        # Required for the QSS :hover pseudo-state to fire on a bare QWidget.
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(t.SPACE_SM, t.SPACE_SM - 1, t.SPACE_SM, t.SPACE_SM - 1)
        outer.setSpacing(t.SPACE_SM)

        outer.addWidget(_Avatar(account["email"]))

        text_col = QVBoxLayout()
        text_col.setSpacing(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(t.SPACE_XS + 2)
        self._email_label = QLabel(account["email"])
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

        outer.addLayout(text_col, stretch=1)
        self._outer = outer
        self._email = account["email"]
        self._collapsed = False
        self._unread = 0
        self._apply_style()

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
        self.setToolTip(self._email if collapsed else "")

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.account_id)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        if selected == self._selected:
            return
        self._selected = selected
        self._apply_style()

    def set_unread(self, count: int) -> None:
        self._unread = max(0, int(count))
        self._refresh_badge()

    def _refresh_badge(self) -> None:
        """One place decides whether the count is on screen.

        Both the unread count and the collapsed state have an opinion here,
        so neither is allowed to call setVisible directly - see the note in
        set_collapsed.
        """
        count = getattr(self, "_unread", 0)
        # 99+ rather than a four-digit pill that resizes the row it is in.
        self._badge.setText(str(count) if count < 100 else "99+")
        self._badge.setVisible(bool(count) and not self._collapsed)

    def set_status(self, status_key: str, text: str) -> None:
        self._status.set_status(status_key, text)

    def _apply_style(self) -> None:
        if self._selected:
            bg = t.BG_SELECTED
        else:
            bg = "transparent"
        self.setStyleSheet(
            f"QWidget#accountItem {{ background: {bg}; border-radius: {t.RADIUS_MD}px; }}"
            f"QWidget#accountItem:hover {{ background: {t.BG_HOVER}; }}"
        )

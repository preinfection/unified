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
        self._apply_style()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.account_id)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        if selected == self._selected:
            return
        self._selected = selected
        self._apply_style()

    def set_unread(self, count: int) -> None:
        self._badge.setText(str(count) if count else "")
        self._badge.setVisible(bool(count))

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

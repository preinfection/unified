"""One connected account in the sidebar.

An account row carries more state than a folder row - identity, unread
count, and a live sync status that changes several times a second during
a first sync - so it is a real composed widget rather than a painted row.
There are only ever a handful on screen, so there is no virtualization
argument against that.

Two decisions worth naming:

* The address is elided from the *left* (`…@example.com`), because when
  two accounts share a provider the distinguishing part is the local
  part, not the domain - and right-elision hides exactly the half that
  tells them apart.
* Sync status is a dot *and* words. During a first sync the words are the
  interesting part ("Downloading 1,240/8,900"), and once it settles the
  row goes quiet rather than leaving a permanent green light burning.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui import theme as t
from app.ui.components.avatar import Avatar
from app.ui.components.badge import CountBadge, StatusDot


class AccountItem(QWidget):
    clicked = Signal(int)  # account_id

    def __init__(self, account: dict, parent=None):
        super().__init__(parent)
        self.account_id = account["id"]
        self.email = account["email"]
        self._selected = False
        self.setObjectName("accountItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Required for the QSS :hover pseudo-state to fire on a bare QWidget.
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(f"Account {self.email}")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(t.SPACE_MD, t.SPACE_SM, t.SPACE_MD, t.SPACE_SM)
        outer.setSpacing(t.SPACE_MD)

        self._avatar = Avatar(t.AVATAR_SM)
        self._avatar.set_identity(account.get("display_name") or "", self.email)
        outer.addWidget(self._avatar, alignment=Qt.AlignmentFlag.AlignVCenter)

        column = QVBoxLayout()
        column.setSpacing(1)

        top = QHBoxLayout()
        top.setSpacing(t.SPACE_SM)
        self._email_label = QLabel(self.email)
        self._email_label.setObjectName("accountEmail")
        self._email_label.setFont(t.make_font("account_label"))
        self._email_label.setToolTip(self.email)
        self._email_label.setMinimumWidth(40)
        top.addWidget(self._email_label, stretch=1)
        self._badge = CountBadge("quiet")
        top.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        column.addLayout(top)

        self._status = StatusDot()
        column.addWidget(self._status)

        outer.addLayout(column, stretch=1)

    # ------------------------------------------------------------- events

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._elide_email()
        super().resizeEvent(event)

    def _elide_email(self) -> None:
        metrics = QFontMetrics(self._email_label.font())
        available = max(40, self._email_label.width())
        self._email_label.setText(
            metrics.elidedText(self.email, Qt.TextElideMode.ElideLeft, available)
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.account_id)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self.account_id)
            event.accept()
            return
        super().keyPressEvent(event)

    # -------------------------------------------------------------- state

    def set_selected(self, selected: bool) -> None:
        if selected == self._selected:
            return
        self._selected = selected
        t.set_variant(self, "state", "selected" if selected else None)
        self._badge.set_tone("accent" if selected and self._badge.text() else "quiet")

    def set_unread(self, count: int) -> None:
        self._badge.set_count(count)
        self._badge.set_tone("accent" if self._selected and count else "quiet")

    def set_status(self, status_key: str, text: str) -> None:
        self._status.set_status(status_key, text)

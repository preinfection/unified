"""Reading pane: an elevated sender-info card (matching the reference's
drawer header treatment) above the message body. Only ever shows fields
Unified actually has - sender, recipients, account, timestamp, and a
generic "has attachment" indicator (the data model has no per-file
attachment list, so no per-file chips are fabricated).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme as t
from app.ui.components.avatar import paint_avatar
from app.ui.html_view import HtmlMailView
from app.ui.svg_icon import icon_set, simple_icon

_AVATAR_SIZE = 40
_ACTION_ICON_SIZE = 16


class _HeaderAvatar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_AVATAR_SIZE, _AVATAR_SIZE)
        self._name = ""
        self._email = ""

    def set_identity(self, name: str, email: str) -> None:
        self._name, self._email = name, email
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        paint_avatar(
            painter, QRectF(0, 0, _AVATAR_SIZE, _AVATAR_SIZE),
            self._email or self._name, self._name, self._email,
        )


class PreviewPane(QWidget):
    star_clicked = Signal()
    delete_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        # -- elevated sender-info card
        card = QWidget()
        card.setObjectName("previewCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        self._avatar = _HeaderAvatar()
        header_row.addWidget(self._avatar)

        identity_col = QVBoxLayout()
        identity_col.setSpacing(1)
        self._sender_name = QLabel("Select an email")
        self._sender_name.setObjectName("heading")
        self._sender_name.setWordWrap(True)
        self._sender_name.setTextFormat(Qt.TextFormat.PlainText)
        # Two separate lines rather than one long "a | b | c" string - a
        # single wrapped QLabel breaks mid-separator and strands lone "|"
        # characters on their own line once the text gets long.
        self._sender_email_line = QLabel("")
        self._sender_email_line.setObjectName("secondary")
        self._sender_email_line.setWordWrap(True)
        self._sender_email_line.setTextFormat(Qt.TextFormat.PlainText)
        self._sender_meta_line = QLabel("")
        self._sender_meta_line.setObjectName("tertiary")
        self._sender_meta_line.setWordWrap(True)
        self._sender_meta_line.setTextFormat(Qt.TextFormat.PlainText)
        identity_col.addWidget(self._sender_name)
        identity_col.addWidget(self._sender_email_line)
        identity_col.addWidget(self._sender_meta_line)
        header_row.addLayout(identity_col, stretch=1)

        self.star_btn = QPushButton(" Star")
        self.star_btn.setObjectName("iconButton")
        self.star_btn.setIconSize(QSize(_ACTION_ICON_SIZE, _ACTION_ICON_SIZE))
        self.star_btn.clicked.connect(self.star_clicked.emit)
        self.delete_btn = QPushButton(" Delete")
        self.delete_btn.setObjectName("iconButton")
        self.delete_btn.setIcon(icon_set(
            "trash", _ACTION_ICON_SIZE, normal=t.ICON_SECONDARY,
            active=t.ERROR, disabled=t.ICON_DISABLED,
        ))
        self.delete_btn.setIconSize(QSize(_ACTION_ICON_SIZE, _ACTION_ICON_SIZE))
        self.delete_btn.clicked.connect(self.delete_clicked.emit)
        for b in (self.star_btn, self.delete_btn):
            b.setEnabled(False)
            header_row.addWidget(b, alignment=Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(header_row)

        self._subject = QLabel("")
        self._subject.setObjectName("heading")
        self._subject.setWordWrap(True)
        self._subject.setTextFormat(Qt.TextFormat.PlainText)
        card_layout.addWidget(self._subject)

        self._attachment_chip = QWidget()
        self._attachment_chip.setObjectName("attachmentChip")
        chip_layout = QHBoxLayout(self._attachment_chip)
        chip_layout.setContentsMargins(10, 4, 12, 4)
        chip_layout.setSpacing(6)
        chip_icon = QLabel()
        chip_icon.setPixmap(simple_icon("attachment", 13, t.TEXT_SECONDARY).pixmap(13, 13))
        chip_layout.addWidget(chip_icon)
        chip_layout.addWidget(QLabel("Has attachment"))
        self._attachment_chip.setVisible(False)
        chip_row = QHBoxLayout()
        chip_row.addWidget(self._attachment_chip)
        chip_row.addStretch(1)
        card_layout.addLayout(chip_row)

        outer.addWidget(card)
        t.apply_soft_shadow(card, blur=28, y_offset=8, alpha=90)

        self.body = HtmlMailView()
        outer.addWidget(self.body, stretch=1)
        self.set_starred(False)  # give the Star button its initial icon

    # ------------------------------------------------------------------ api

    def show_placeholder(self, title: str, body_text: str = "") -> None:
        self._sender_name.setText(title)
        self._sender_email_line.setText("")
        self._sender_meta_line.setText("")
        self._subject.setText("")
        self._attachment_chip.setVisible(False)
        self._avatar.set_identity("", "")
        self.set_actions_enabled(False)
        if body_text:
            self.body.set_email_text(body_text)
        else:
            self.body.set_email_text("")

    def show_message(
        self, *, subject: str, sender_name: str, sender_email: str,
        recipients: str, account_email: str, time_text: str,
        has_attachments: bool, is_starred: bool,
    ) -> None:
        display_name = sender_name or sender_email or "(unknown sender)"
        self._sender_name.setText(display_name)

        email_line = sender_email if sender_email and sender_email != display_name else ""
        if recipients:
            email_line = f"{email_line}   ·   To: {recipients}" if email_line else f"To: {recipients}"
        self._sender_email_line.setText(email_line)
        self._sender_email_line.setVisible(bool(email_line))

        self._sender_meta_line.setText(f"{account_email}  ·  {time_text}")
        self._subject.setText(subject or "(no subject)")
        self._avatar.set_identity(sender_name, sender_email)
        self._attachment_chip.setVisible(has_attachments)
        self.set_actions_enabled(True)
        self.set_starred(is_starred)

    def set_actions_enabled(self, enabled: bool) -> None:
        self.star_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)

    def set_starred(self, starred: bool) -> None:
        self.star_btn.setText(" Unstar" if starred else " Star")
        icon_name = "star_filled" if starred else "star_outline"
        color = t.STARRED if starred else t.ICON_SECONDARY
        self.star_btn.setIcon(icon_set(
            icon_name, _ACTION_ICON_SIZE, normal=color, active=t.STARRED,
            disabled=t.ICON_DISABLED,
        ))

    def set_attachment_visible(self, visible: bool) -> None:
        self._attachment_chip.setVisible(visible)

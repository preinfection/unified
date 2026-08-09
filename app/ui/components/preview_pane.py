"""Reading pane: an elevated sender-info card above the message body when
a message is open, or a quiet centered empty state when nothing is
selected - never a half-empty card with blank fields. Only ever shows
fields Unified actually has - sender, recipients, account, timestamp,
and a generic "has attachment" indicator (the data model has no per-file
attachment list, so no per-file chips are fabricated).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme as t
from app.ui.components.avatar import paint_avatar
from app.ui.html_view import HtmlMailView
from app.ui.svg_icon import icon_set, simple_icon

_AVATAR_SIZE = 42


def _human_size(num_bytes: int) -> str:
    if num_bytes <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return ""


def _format_attachment_label(att: dict) -> str:
    name = att.get("name") or "attachment"
    size = _human_size(int(att.get("size") or 0))
    label = f"{name}  ({size})" if size else name
    if att.get("verdict") == "block":
        label += "  -  blocked"
    return label


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


class _EmptyState(QWidget):
    """Shown when no message is selected - a real placeholder, not a
    mostly-blank card. `set_text` lets MainWindow reuse this for the
    "message unavailable" case too."""

    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.addStretch(2)

        icon = QLabel()
        icon.setPixmap(simple_icon("paper", 40, t.BORDER_LIGHT).pixmap(40, 40))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(icon)
        col.addSpacing(t.SPACE_MD)

        self._title = QLabel("Select a message")
        self._title.setFont(t.make_font("dialog_heading"))
        self._title.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._title)

        self._detail = QLabel("Choose an email from the list to read it here.")
        self._detail.setFont(t.make_font("body"))
        self._detail.setStyleSheet(f"color: {t.TEXT_TERTIARY};")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        col.addWidget(self._detail)
        col.addStretch(3)

    def set_text(self, title: str, detail: str) -> None:
        self._title.setText(title)
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))


class PreviewPane(QWidget):
    star_clicked = Signal()
    delete_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        self._empty = _EmptyState()
        self._stack.addWidget(self._empty)

        message_page = QWidget()
        page_col = QVBoxLayout(message_page)
        page_col.setContentsMargins(t.SPACE_LG - 2, t.SPACE_MD, t.SPACE_LG - 2, t.SPACE_MD)
        page_col.setSpacing(t.SPACE_SM + 2)

        # -- elevated sender-info card
        card = QWidget()
        card.setObjectName("previewCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(t.SPACE_LG, t.SPACE_MD + 2, t.SPACE_LG, t.SPACE_MD + 2)
        card_layout.setSpacing(t.SPACE_SM + 2)

        header_row = QHBoxLayout()
        header_row.setSpacing(t.SPACE_MD)
        self._avatar = _HeaderAvatar()
        header_row.addWidget(self._avatar)

        identity_col = QVBoxLayout()
        identity_col.setSpacing(1)
        self._sender_name = QLabel("")
        self._sender_name.setFont(t.make_font("sender"))
        self._sender_name.setStyleSheet(f"color: {t.TEXT_PRIMARY};")
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
        self.star_btn.setFont(t.make_font("button"))
        self.star_btn.setIconSize(QSize(t.ICON_SIZE_ACTION, t.ICON_SIZE_ACTION))
        self.star_btn.clicked.connect(self.star_clicked.emit)
        self.delete_btn = QPushButton(" Delete")
        self.delete_btn.setObjectName("iconButton")
        self.delete_btn.setFont(t.make_font("button"))
        self.delete_btn.setIcon(icon_set(
            "trash", t.ICON_SIZE_ACTION, normal=t.ICON_SECONDARY,
            active=t.ERROR, disabled=t.ICON_DISABLED,
        ))
        self.delete_btn.setIconSize(QSize(t.ICON_SIZE_ACTION, t.ICON_SIZE_ACTION))
        self.delete_btn.clicked.connect(self.delete_clicked.emit)
        for b in (self.star_btn, self.delete_btn):
            b.setEnabled(False)
            header_row.addWidget(b, alignment=Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(header_row)

        self._subject = QLabel("")
        self._subject.setFont(t.make_font("dialog_heading"))
        self._subject.setStyleSheet(f"color: {t.TEXT_PRIMARY};")
        self._subject.setWordWrap(True)
        self._subject.setTextFormat(Qt.TextFormat.PlainText)
        card_layout.addWidget(self._subject)

        self._attachment_chip = QWidget()
        self._attachment_chip.setObjectName("attachmentChip")
        chip_layout = QHBoxLayout(self._attachment_chip)
        chip_layout.setContentsMargins(t.SPACE_SM + 2, t.SPACE_XS, t.SPACE_MD, t.SPACE_XS)
        chip_layout.setSpacing(t.SPACE_XS + 2)
        chip_icon = QLabel()
        chip_icon.setPixmap(simple_icon("attachment", t.ICON_SIZE_ROW, t.TEXT_SECONDARY)
                            .pixmap(t.ICON_SIZE_ROW, t.ICON_SIZE_ROW))
        chip_layout.addWidget(chip_icon)
        chip_text = QLabel("Has attachment")
        chip_text.setFont(t.make_font("caption"))
        chip_layout.addWidget(chip_text)
        self._attachment_chip.setVisible(False)
        chip_row = QHBoxLayout()
        chip_row.addWidget(self._attachment_chip)
        chip_row.addStretch(1)
        card_layout.addLayout(chip_row)

        # Per-file attachment chips, each carrying the attachment guard's
        # verdict. Replaces the generic "Has attachment" indicator when
        # real per-file metadata is available.
        self._attachment_list = QVBoxLayout()
        self._attachment_list.setSpacing(t.SPACE_XS)
        self._attachment_list.setContentsMargins(0, 0, 0, 0)
        card_layout.addLayout(self._attachment_list)

        page_col.addWidget(card)
        t.apply_elevation(card, "sm")

        # Privacy bar: remote images are withheld until asked for, so the
        # user is told plainly rather than left wondering why a
        # newsletter looks empty.
        self._images_bar = QWidget()
        self._images_bar.setObjectName("blockedImagesBar")
        bar_row = QHBoxLayout(self._images_bar)
        bar_row.setContentsMargins(t.SPACE_MD, t.SPACE_XS + 2, t.SPACE_SM, t.SPACE_XS + 2)
        bar_row.setSpacing(t.SPACE_SM)
        bar_icon = QLabel()
        bar_icon.setPixmap(simple_icon("shield", 14, t.WARNING).pixmap(14, 14))
        bar_row.addWidget(bar_icon)
        self._images_label = QLabel("Remote images blocked to protect your privacy")
        self._images_label.setFont(t.make_font("caption"))
        self._images_label.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
        bar_row.addWidget(self._images_label, stretch=1)
        self._show_images_btn = QPushButton("Show images")
        self._show_images_btn.setObjectName("iconButton")
        self._show_images_btn.setFont(t.make_font("caption"))
        self._show_images_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_images_btn.clicked.connect(self._on_show_images)
        bar_row.addWidget(self._show_images_btn)
        self._images_bar.setVisible(False)
        page_col.addWidget(self._images_bar)

        self.body = HtmlMailView()
        self.body.setObjectName("emailBody")
        self.body.remote_images_blocked.connect(self._on_remote_images_blocked)
        page_col.addWidget(self.body, stretch=1)
        t.apply_elevation(self.body, "sm")
        self._stack.addWidget(message_page)

        self.set_starred(False)  # give the Star button its initial icon
        self._stack.setCurrentWidget(self._empty)

    # ------------------------------------------------------------------ api

    def show_placeholder(self, title: str, body_text: str = "") -> None:
        self._empty.set_text(title, body_text)
        self._stack.setCurrentWidget(self._empty)
        self.set_actions_enabled(False)

    def reset(self) -> None:
        """Back to the default "nothing selected" empty state."""
        self.show_placeholder(
            "Select a message", "Choose an email from the list to read it here."
        )

    def show_message(
        self, *, subject: str, sender_name: str, sender_email: str,
        recipients: str, account_email: str, time_text: str,
        has_attachments: bool, is_starred: bool,
    ) -> None:
        # New message: image consent starts fresh (see
        # HtmlMailView.set_email_html), so the bar must start hidden too.
        self._images_bar.setVisible(False)
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
        self._stack.setCurrentIndex(1)

    def set_actions_enabled(self, enabled: bool) -> None:
        self.star_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)

    def set_starred(self, starred: bool) -> None:
        self.star_btn.setText(" Unstar" if starred else " Star")
        icon_name = "star_filled" if starred else "star_outline"
        color = t.STARRED if starred else t.ICON_SECONDARY
        self.star_btn.setIcon(icon_set(
            icon_name, t.ICON_SIZE_ACTION, normal=color, active=t.STARRED,
            disabled=t.ICON_DISABLED,
        ))

    def set_attachment_visible(self, visible: bool) -> None:
        self._attachment_chip.setVisible(visible)

    # -------------------------------------------------------- attachments

    def set_attachments(self, attachments: list[dict]) -> None:
        """Render one chip per attachment, coloured by the guard's verdict.

        A blocked attachment is shown with its reason rather than hidden -
        silently dropping it would leave the user wondering where the file
        went, and the name shown is always the guard's sanitized form.
        """
        while self._attachment_list.count():
            item = self._attachment_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if not attachments:
            return
        # Per-file chips supersede the generic indicator.
        self._attachment_chip.setVisible(False)

        for att in attachments:
            verdict = att.get("verdict", "allow")
            blocked = verdict == "block"
            warn = verdict == "warn"
            color = t.ERROR if blocked else (t.WARNING if warn else t.TEXT_SECONDARY)
            icon_name = "warning" if (blocked or warn) else "attachment"

            chip = QWidget()
            chip.setObjectName("attachmentChip")
            row = QHBoxLayout(chip)
            row.setContentsMargins(t.SPACE_SM + 2, t.SPACE_XS, t.SPACE_MD, t.SPACE_XS)
            row.setSpacing(t.SPACE_XS + 2)

            icon = QLabel()
            icon.setPixmap(simple_icon(icon_name, t.ICON_SIZE_ROW, color)
                           .pixmap(t.ICON_SIZE_ROW, t.ICON_SIZE_ROW))
            row.addWidget(icon)

            label = QLabel(_format_attachment_label(att))
            label.setFont(t.make_font("caption"))
            label.setStyleSheet(f"color: {color};")
            label.setTextFormat(Qt.TextFormat.PlainText)
            row.addWidget(label)

            reason = att.get("reason") or ""
            if reason:
                chip.setToolTip(
                    ("Blocked: " if blocked else "Caution: ") + reason
                )
            row.addStretch(1)

            wrapper = QHBoxLayout()
            wrapper.addWidget(chip)
            wrapper.addStretch(1)
            holder = QWidget()
            holder.setLayout(wrapper)
            self._attachment_list.addWidget(holder)

    # ------------------------------------------------------ remote images

    def _on_remote_images_blocked(self, count: int) -> None:
        plural = "s" if count != 1 else ""
        self._images_label.setText(
            f"{count} remote image{plural} blocked to protect your privacy"
        )
        self._images_bar.setVisible(True)

    def _on_show_images(self) -> None:
        self.body.set_remote_images_allowed(True)
        self._images_bar.setVisible(False)

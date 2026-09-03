"""The reading pane.

The one screen in a mail client where the app should get out of the way.
So this is the least decorated surface in the product: no card, no
elevation, no border around the message body. The body sits directly on
the pane, because email content *is* the content - wrapping it in a
rounded panel makes a letter look like a dashboard tile.

Anatomy:

    ── actions ─────────────────────────────  Reply / Forward / Star / …
       Subject                                a real heading, not a field
       [AV] Sender Name  <address>   time
            To: …                             expandable, never truncated away
       [attachment chips] [privacy banner]
    ───────────────────────────────────────
       message body                           generous margins, measured line length

Details that carry more than their size suggests:

* Actions are grouped by consequence: reply/forward (composing) on the
  left, state changes (star, unread) next, destructive (delete) last and
  separated. Delete never sits adjacent to Reply.
* The timestamp is absolute and complete ("Tue, 4 Mar 2025 at 09:14"),
  not "2d ago". In mail, the exact time is frequently the point.
* Recipients collapse to one line with a real expander rather than being
  elided into oblivion - "who else got this" is a question mail clients
  are asked constantly.
* Remote images stay blocked until asked for, and the pane says so in a
  banner with a button, because a newsletter that renders blank with no
  explanation reads as a broken app rather than as privacy protection.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QVariantAnimation, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme as t
from app.ui.components.avatar import Avatar
from app.ui.components.buttons import Button, IconButton
from app.ui.components.dialog import divider
from app.ui.components.states import EmptyState
from app.ui.design import motion
from app.ui.design.motion import ValueAnimator
from app.ui.html_view import HtmlMailView
from app.ui.svg_icon import themed, themed_pixmap


def _human_size(num_bytes: int) -> str:
    if num_bytes <= 0:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return ""


def _attachment_label(att: dict) -> str:
    name = att.get("name") or "attachment"
    size = _human_size(int(att.get("size") or 0))
    return f"{name}  ·  {size}" if size else name


class _Banner(QWidget):
    """A one-line notice attached to the message, with its action inline."""

    def __init__(self, icon: str, tone: str, text: str, action_text: str = "",
                 parent=None):
        super().__init__(parent)
        self.setProperty("role", "banner")
        self.setProperty("tone", tone)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(t.SPACE_LG, t.SPACE_SM, t.SPACE_MD, t.SPACE_SM)
        row.setSpacing(t.SPACE_MD)

        self._icon_name = icon
        self._icon_role = tone if tone in ("warning", "danger", "success") else "default"
        self._icon = QLabel()
        self._icon.setPixmap(themed_pixmap(icon, t.ICON_SM, self._icon_role))
        row.addWidget(self._icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.label = QLabel(text)
        self.label.setFont(t.make_font("body_sm"))
        self.label.setWordWrap(True)
        row.addWidget(self.label, stretch=1)

        self.action = Button(action_text, variant="link", size="sm")
        self.action.setVisible(bool(action_text))
        row.addWidget(self.action, alignment=Qt.AlignmentFlag.AlignVCenter)

    def refresh_icon(self) -> None:
        self._icon.setPixmap(themed_pixmap(self._icon_name, t.ICON_SM, self._icon_role))


class ReaderPane(QWidget):
    star_clicked = Signal()
    delete_clicked = Signal()
    reply_clicked = Signal()
    reply_all_clicked = Signal()
    forward_clicked = Signal()
    mark_unread_clicked = Signal()
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("readerPane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(t.READER_WIDTH_MIN)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        self._empty = EmptyState()
        self._empty.set_state(
            icon="reader", title="No message selected",
            detail="Pick a message from the list to read it here.",
        )
        self._stack.addWidget(self._empty)
        self._stack.addWidget(self._build_message_page())
        self._stack.setCurrentWidget(self._empty)

        self.set_starred(False)
        self.set_actions_enabled(False)

        # 1 -> the header is still arriving, 0 -> settled.
        self._reveal = ValueAnimator(self, 0.0, motion.DURATION_VERY_SLOW,
                                     motion.EASE_SMOOTH_OUT)

    # ------------------------------------------------------------- build

    def _build_message_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(self._build_action_bar())

        header = QWidget()
        header.setObjectName("readerHeader")
        head = QVBoxLayout(header)
        head.setContentsMargins(t.SPACE_3XL, t.SPACE_XL, t.SPACE_3XL, t.SPACE_XL)
        head.setSpacing(t.SPACE_LG)

        self._subject = QLabel("")
        self._subject.setFont(t.make_font("title"))
        self._subject.setWordWrap(True)
        self._subject.setTextFormat(Qt.TextFormat.PlainText)
        self._subject.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        head.addWidget(self._subject)

        identity = QHBoxLayout()
        identity.setSpacing(t.SPACE_LG)
        self._avatar = Avatar(t.AVATAR_LG)
        identity.addWidget(self._avatar, alignment=Qt.AlignmentFlag.AlignTop)

        who = QVBoxLayout()
        who.setSpacing(1)

        name_row = QHBoxLayout()
        name_row.setSpacing(t.SPACE_MD)
        self._sender_name = QLabel("")
        self._sender_name.setFont(t.make_font("body_strong"))
        self._sender_name.setTextFormat(Qt.TextFormat.PlainText)
        name_row.addWidget(self._sender_name)
        self._sender_email = QLabel("")
        self._sender_email.setProperty("tone", "tertiary")
        self._sender_email.setFont(t.make_font("body_sm"))
        self._sender_email.setTextFormat(Qt.TextFormat.PlainText)
        # The address gives up width first: it is already repeated in the
        # avatar and the reply target, whereas a half-printed timestamp
        # ("Wed, 02 Sep 2026 at 22:4") is just wrong.
        self._sender_email.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._sender_email.setMinimumWidth(0)
        name_row.addWidget(self._sender_email, stretch=1)
        self._timestamp = QLabel("")
        self._timestamp.setProperty("tone", "tertiary")
        self._timestamp.setFont(t.make_font("caption"))
        self._timestamp.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred
        )
        name_row.addWidget(self._timestamp, alignment=Qt.AlignmentFlag.AlignRight)
        who.addLayout(name_row)

        recipients_row = QHBoxLayout()
        recipients_row.setSpacing(t.SPACE_SM)
        self._recipients = QLabel("")
        self._recipients.setProperty("tone", "secondary")
        self._recipients.setFont(t.make_font("body_sm"))
        self._recipients.setTextFormat(Qt.TextFormat.PlainText)
        self._recipients.setWordWrap(False)
        recipients_row.addWidget(self._recipients)
        self._expand_recipients = Button("Details", variant="link", size="sm")
        self._expand_recipients.clicked.connect(self._toggle_recipients)
        recipients_row.addWidget(self._expand_recipients)
        recipients_row.addStretch(1)
        who.addLayout(recipients_row)

        self._account_line = QLabel("")
        self._account_line.setProperty("tone", "tertiary")
        self._account_line.setFont(t.make_font("caption"))
        self._account_line.setVisible(False)
        who.addWidget(self._account_line)

        identity.addLayout(who, stretch=1)
        head.addLayout(identity)

        self._attachments = QVBoxLayout()
        self._attachments.setSpacing(t.SPACE_SM)
        head.addLayout(self._attachments)

        self._images_banner = _Banner(
            "eye", "warning",
            "Remote images are blocked to protect your privacy",
            "Show images",
        )
        self._images_banner.action.clicked.connect(self._on_show_images)
        self._images_banner.setVisible(False)
        head.addWidget(self._images_banner)

        column.addWidget(header)
        column.addWidget(divider())

        self.body = HtmlMailView()
        self.body.setObjectName("emailBody")
        self.body.remote_images_blocked.connect(self._on_remote_images_blocked)
        self.body.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        column.addWidget(self.body, stretch=1)

        self._recipients_expanded = False
        self._full_recipients = ""
        return page

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("readerHeader")
        bar.setFixedHeight(t.READER_HEADER_HEIGHT)
        row = QHBoxLayout(bar)
        row.setContentsMargins(t.SPACE_LG, t.SPACE_SM, t.SPACE_LG, t.SPACE_SM)
        row.setSpacing(t.SPACE_SM)

        self.back_button = IconButton("arrow_left", "Back to the list", size="sm")
        self.back_button.clicked.connect(self.back_clicked.emit)
        self.back_button.setVisible(False)
        row.addWidget(self.back_button)

        self.reply_button = Button(
            "Reply", variant="subtle", size="sm", icon="reply",
            tooltip="Reply to the sender (R)",
        )
        self.reply_button.clicked.connect(self.reply_clicked.emit)
        row.addWidget(self.reply_button)

        self.reply_all_button = Button(
            "Reply all", variant="subtle", size="sm", icon="reply_all",
            tooltip="Reply to everyone (Shift+R)",
        )
        self.reply_all_button.clicked.connect(self.reply_all_clicked.emit)
        row.addWidget(self.reply_all_button)

        self.forward_button = Button(
            "Forward", variant="subtle", size="sm", icon="forward",
            tooltip="Forward this message (F)",
        )
        self.forward_button.clicked.connect(self.forward_clicked.emit)
        row.addWidget(self.forward_button)

        row.addStretch(1)

        self.star_button = IconButton("star_outline", "Star this message (S)", size="sm")
        self.star_button.clicked.connect(self.star_clicked.emit)
        row.addWidget(self.star_button)

        self.unread_button = IconButton(
            "mail", "Mark as unread (U)", size="sm"
        )
        self.unread_button.clicked.connect(self.mark_unread_clicked.emit)
        row.addWidget(self.unread_button)

        self.more_button = IconButton("more_horizontal", "More actions", size="sm")
        self.more_button.clicked.connect(self._show_more_menu)
        row.addWidget(self.more_button)

        # Destructive actions are separated from everything else, so
        # "delete" is never the button next to "reply" in muscle memory.
        row.addSpacing(t.SPACE_MD)
        self.delete_button = IconButton(
            "trash", "Move to trash (Del)", size="sm", icon_role="danger",
        )
        self.delete_button.clicked.connect(self.delete_clicked.emit)
        row.addWidget(self.delete_button)
        return bar

    # ------------------------------------------------------------ actions

    def _show_more_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(
            themed("mail", t.ICON_SM, "default"), "Mark as unread",
            self.mark_unread_clicked.emit,
        )
        menu.addAction(
            themed("user", t.ICON_SM, "default"), "Copy sender address",
            self._copy_sender,
        )
        menu.exec(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))

    def _copy_sender(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._sender_email_value)

    def _toggle_recipients(self) -> None:
        self._recipients_expanded = not self._recipients_expanded
        self._render_recipients()
        self._expand_recipients.setText(
            "Hide" if self._recipients_expanded else "Details"
        )

    def _render_recipients(self) -> None:
        text = self._full_recipients
        if not text:
            self._recipients.setText("")
            self._expand_recipients.setVisible(False)
            return
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if self._recipients_expanded or len(parts) <= 1:
            self._recipients.setWordWrap(True)
            self._recipients.setText("To: " + ", ".join(parts))
        else:
            self._recipients.setWordWrap(False)
            extra = len(parts) - 1
            self._recipients.setText(f"To: {parts[0]} +{extra} more")
        self._recipients.setToolTip("To: " + ", ".join(parts))
        self._expand_recipients.setVisible(len(parts) > 1)

    # ---------------------------------------------------------------- api

    def show_placeholder(self, title: str, body_text: str = "") -> None:
        self._empty.set_state(icon="reader", title=title, detail=body_text)
        self._stack.setCurrentWidget(self._empty)
        self.set_actions_enabled(False)

    def reset(self) -> None:
        self.show_placeholder(
            "No message selected", "Pick a message from the list to read it here."
        )

    def show_message(
        self, *, subject: str, sender_name: str, sender_email: str,
        recipients: str, account_email: str, time_text: str,
        has_attachments: bool, is_starred: bool, show_account: bool = True,
    ) -> None:
        # Image consent is per message (see HtmlMailView.set_email_html),
        # so the banner must start hidden for every new message.
        self._images_banner.setVisible(False)
        display_name = sender_name or sender_email or "(unknown sender)"
        self._sender_email_value = sender_email

        self._subject.setText(subject or "(no subject)")
        self._sender_name.setText(display_name)
        self._sender_address_text = (
            sender_email if sender_email and sender_email != display_name else ""
        )
        self._sender_email.setToolTip(self._sender_address_text)
        self._elide_sender_address()
        self._timestamp.setText(time_text)
        self._timestamp.setToolTip(time_text)
        self._avatar.set_identity(sender_name, sender_email)

        self._full_recipients = recipients or ""
        self._recipients_expanded = False
        self._expand_recipients.setText("Details")
        self._render_recipients()

        self._account_line.setText(f"Received by {account_email}")
        self._account_line.setVisible(bool(account_email) and show_account)

        self.set_actions_enabled(True)
        self.set_starred(is_starred)
        self._play_reveal()
        if has_attachments and not self._attachments.count():
            self.set_attachments([{"name": "Attachment"}])
        self._stack.setCurrentIndex(1)

    def _apply_measure(self) -> None:
        """Cap the message body's line length.

        Text set 1,100px wide is not a wide column, it is an unreadable
        one: the eye loses the line it was on during the return sweep.
        Extra width past the measure becomes symmetric margin, so a
        maximised window gives the message more air rather than longer
        lines.
        """
        overflow = self.width() - t.READER_MAX_TEXT_WIDTH
        margin = max(0, overflow // 2)
        if getattr(self, "_measure_margin", None) != margin:
            self._measure_margin = margin
            self.body.setViewportMargins(margin, 0, margin, 0)

    def _elide_sender_address(self) -> None:
        from PySide6.QtGui import QFontMetrics

        text = getattr(self, "_sender_address_text", "")
        metrics = QFontMetrics(self._sender_email.font())
        available = max(0, self._sender_email.width())
        self._sender_email.setText(
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, available)
            if available else text
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._elide_sender_address()
        self._apply_measure()
        super().resizeEvent(event)

    def _play_reveal(self) -> None:
        """Rise the header lines into place as the message arrives."""
        self._reveal.set_now(1.0)
        self._reveal.to(0.0)
        for index, widget in enumerate(
            (self._subject, self._sender_name, self._recipients)
        ):
            self._animate_line(widget, index)

    def _animate_line(self, widget, index: int) -> None:
        """One line of the header rising into place, `index` steps late."""
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        duration = t.duration(motion.DURATION_VERY_SLOW)
        if duration <= 0:
            widget.setGraphicsEffect(None)
            return

        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)

        def run():
            try:
                fade = QVariantAnimation(widget)
            except RuntimeError:
                return
            fade.setDuration(duration)
            fade.setEasingCurve(motion.EASE_SMOOTH_OUT)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.valueChanged.connect(lambda v: effect.setOpacity(float(v)))
            # The effect is dropped once it has done its job: leaving a
            # QGraphicsEffect installed on a label costs a repaint through
            # a software raster path for the rest of its life.
            fade.finished.connect(lambda: widget.setGraphicsEffect(None))
            fade.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

        QTimer.singleShot(motion.stagger_delay(index, 3), run)

    def set_actions_enabled(self, enabled: bool) -> None:
        for button in (
            self.star_button, self.delete_button, self.reply_button,
            self.reply_all_button, self.forward_button, self.unread_button,
            self.more_button,
        ):
            button.setEnabled(enabled)

    def set_starred(self, starred: bool) -> None:
        self.star_button.set_icon(
            "star_filled" if starred else "star_outline",
            "star" if starred else "default",
        )
        self.star_button.setToolTip(
            "Remove star (S)" if starred else "Star this message (S)"
        )
        self.star_button.setAccessibleName(
            "Starred" if starred else "Not starred"
        )

    def set_attachment_visible(self, visible: bool) -> None:
        if visible and not self._attachments.count():
            self.set_attachments([{"name": "Attachment"}])
        elif not visible:
            self.set_attachments([])

    def set_back_visible(self, visible: bool) -> None:
        """Shown only in the stacked (narrow-window) layout, where the
        list is not on screen next to the message."""
        self.back_button.setVisible(visible)

    def set_compact(self, compact: bool) -> None:
        """Under a narrow reading pane the reply actions lose their labels
        before they lose their place - the alternative is a row of
        buttons that silently overflows off the right edge."""
        for button, label in (
            (self.reply_button, "Reply"),
            (self.reply_all_button, "Reply all"),
            (self.forward_button, "Forward"),
        ):
            button.setText("" if compact else label)
            button.setProperty("shape", "icon" if compact else None)
            t.repolish(button)

    # -------------------------------------------------------- attachments

    def set_attachments(self, attachments: list[dict]) -> None:
        """One chip per file, carrying the attachment guard's verdict.

        A blocked attachment is shown with its reason rather than hidden:
        silently dropping it leaves the user wondering where the file
        went. The name shown is always the guard's sanitized form.
        """
        while self._attachments.count():
            item = self._attachments.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if not attachments:
            return

        row_holder = QWidget()
        row = QHBoxLayout(row_holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(t.SPACE_SM)
        for att in attachments:
            row.addWidget(self._attachment_chip(att))
        row.addStretch(1)
        self._attachments.addWidget(row_holder)

    def _attachment_chip(self, att: dict) -> QWidget:
        verdict = att.get("verdict", "allow")
        blocked = verdict == "block"
        warn = verdict == "warn"
        tone = "danger" if blocked else ("warning" if warn else "default")
        icon_name = "warning" if (blocked or warn) else "attachment"
        icon_role = "danger" if blocked else ("warning" if warn else "quiet")

        chip = QWidget()
        chip.setProperty("role", "chip")
        if tone != "default":
            chip.setProperty("tone", tone)
        row = QHBoxLayout(chip)
        row.setContentsMargins(t.SPACE_MD, t.SPACE_XS, t.SPACE_LG, t.SPACE_XS)
        row.setSpacing(t.SPACE_SM)

        icon = QLabel()
        icon.setPixmap(themed_pixmap(icon_name, t.ICON_SM, icon_role))
        row.addWidget(icon)

        label = QLabel(_attachment_label(att))
        label.setFont(t.make_font("caption"))
        label.setTextFormat(Qt.TextFormat.PlainText)
        if blocked:
            label.setProperty("tone", "danger")
        elif warn:
            label.setProperty("tone", "warning")
        row.addWidget(label)

        reason = att.get("reason") or ""
        if blocked:
            row.addWidget(self._chip_note("blocked"))
        if reason:
            chip.setToolTip(("Blocked: " if blocked else "Caution: ") + reason)
        return chip

    @staticmethod
    def _chip_note(text: str) -> QLabel:
        note = QLabel(text)
        note.setProperty("tone", "danger")
        note.setFont(t.make_font("caption_strong"))
        return note

    # ------------------------------------------------------ remote images

    def _on_remote_images_blocked(self, count: int) -> None:
        plural = "s" if count != 1 else ""
        self._images_banner.label.setText(
            f"{count} remote image{plural} blocked to protect your privacy"
        )
        self._images_banner.setVisible(True)

    def _on_show_images(self) -> None:
        self.body.set_remote_images_allowed(True)
        self._images_banner.setVisible(False)

    # ------------------------------------------------------------- theme

    def refresh_icons(self) -> None:
        for button in (
            self.back_button, self.reply_button, self.reply_all_button,
            self.forward_button, self.star_button, self.unread_button,
            self.more_button, self.delete_button,
        ):
            button.refresh_icon()
        self._images_banner.refresh_icon()
        self._empty.refresh_icon()


# The pre-redesign name for this surface.
PreviewPane = ReaderPane

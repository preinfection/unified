"""Reading pane: a page with a title, an attribution line, a row of
actions, and the message itself.

=========================================================================
THE HIERARCHY IS THE CHANGE. It used to open with the sender.

    [avatar]  Ada Lovelace                        [Star] [Delete]
              ada@analytical.org
              ada@analytical.org . 18:33
    Re: the engine notes
    [Has attachment]

Four lines of metadata, then the subject, in a bordered card with a drop
shadow under it. Three things wrong, in order of how much they cost:

  * THE SUBJECT IS THE TITLE OF THE DOCUMENT and it was the fifth line,
    set below three repetitions of an address. PRODUCT.md says the reading
    pane is a page; a page leads with its title. What the reader wants
    first is "what is this", and only then "who sent it".
  * The address appeared twice - once under the name, once again beside
    the timestamp - because two separate lines were each assembled from
    whichever fields happened to be present.
  * It was a CARD. A bordered, shadowed, rounded container around body
    text is a container pretending to be a document, and in light mode it
    read as a white box floating on parchment. There is one surface here
    now, and the divisions in it are hairlines.

So: subject, then one attribution line, then the actions, then the body.

=========================================================================
THE ACTIONS ARE THE OTHER CHANGE. There were two - star and delete - and
the reading pane is where a mail client answers "what can I do next?".
Reply, Reply all and Forward now sit at the left, where the eye lands
after finishing the message; the state actions (star, mark unread, delete)
sit at the right, separated by the stretch. Two groups, because "send
something" and "file this" are different intentions and interleaving them
makes both slower to find.

NO ARCHIVE BUTTON, DELIBERATELY. This product's folder vocabulary is
exactly inbox/sent/trash - db.check_and_repair() deletes rows in any other
folder as corrupt. An Archive control would need a schema change, a sync
change and an IMAP move behind it; drawing one that quietly did nothing,
or that silently meant "trash", would be worse than not offering it.

Icon-only with mandatory tooltips and accessible names, which is what
native desktop clients do for secondary actions - a row of eight labelled
buttons would be a web toolbar and would not fit a narrow pane.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui import motion, theme as t
from app.ui.components.avatar import paint_avatar
from app.ui.components.primitives import (
    ClampedLabel,
    ElidingLabel,
    IconButton,
    Rule,
)
from app.ui.html_view import HtmlMailView
from app.ui.svg_icon import simple_icon

_AVATAR_SIZE = 36

# The reading pane's own left margin. Named because the title, the
# attribution, the actions and the body all have to share it exactly - a
# page whose title starts 2px left of its body reads as broken even when
# nobody can say why.
_PAGE_INSET = t.SPACE_XL

# A subject is untrusted input, like everything else in a message, and the
# title is the one element here allowed to wrap. Left uncapped, a sender
# can push the attribution, the actions and the body off the pane simply
# by writing a very long Subject header - roughly four lines at a typical
# pane width, which is generous for a real subject and short of a wall.
# The rest is elided rather than clipped, so the truncation reads as a
# decision instead of a rendering fault.
_SUBJECT_MAX_CHARS = 240


def _human_size(num_bytes: int) -> str:
    if num_bytes <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return ""


def _clamp_subject(subject: str) -> str:
    """The title, bounded. See _SUBJECT_MAX_CHARS."""
    subject = (subject or "").strip()
    if not subject:
        return "(no subject)"
    if len(subject) <= _SUBJECT_MAX_CHARS:
        return subject
    return subject[:_SUBJECT_MAX_CHARS].rstrip() + "…"


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

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        paint_avatar(
            painter, QRectF(0, 0, _AVATAR_SIZE, _AVATAR_SIZE),
            self._email or self._name, self._name, self._email,
        )


class _EmptyState(QWidget):
    """Shown when no message is selected.

    QUIETER THAN THE LIST'S EMPTY STATE, ON PURPOSE. Both panes are empty
    at the same moment on a fresh install, and they used to say two things
    at identical weight: "No accounts yet / Add account" in the middle and
    "Select a message / Choose an email from the list to read it here" on
    the right. Two headings, two paragraphs, one of them instructions for a
    list with nothing in it. The eye had no idea which mattered.

    This one is secondary text at body size with no heading and no icon, so
    it reads as a label on an empty surface rather than a second offer. And
    when the app has no accounts at all it says nothing whatever - see
    set_silent(). One screen, one primary message.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setSpacing(0)
        col.addStretch(5)

        self._title = QLabel("Select a message")
        self._title.setFont(t.make_font("body"))
        t.role(self._title, "secondary")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._title)
        col.addSpacing(t.SPACE_XS)

        self._detail = QLabel("")
        self._detail.setFont(t.make_font("caption"))
        t.role(self._detail, "tertiary")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        col.addWidget(self._detail)
        col.addStretch(6)

    def set_text(self, title: str, detail: str) -> None:
        self._title.setText(title)
        self._title.setVisible(bool(title))
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))

    def set_silent(self, silent: bool) -> None:
        """Blank the pane entirely.

        For the one moment where the middle column is already making the
        only offer on screen (no accounts yet): a second instruction here
        would compete with it.
        """
        if silent:
            self._title.setVisible(False)
            self._detail.setVisible(False)
        else:
            self.set_text("Select a message",
                          "Pick one from the list to read it here.")


class PreviewPane(QWidget):
    star_clicked = Signal()
    delete_clicked = Signal()
    reply_clicked = Signal()
    reply_all_clicked = Signal()
    forward_clicked = Signal()
    mark_unread_clicked = Signal()

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
        page_col.setContentsMargins(0, 0, 0, 0)
        page_col.setSpacing(0)

        # ---------------------------------------------------------- header
        header = QWidget()
        header.setObjectName("previewHeader")
        head_col = QVBoxLayout(header)
        head_col.setContentsMargins(
            _PAGE_INSET, t.SPACE_LG, _PAGE_INSET, t.SPACE_MD
        )
        head_col.setSpacing(t.SPACE_MD)

        # THE TITLE. First thing, largest thing, and the only thing on the
        # page allowed to be this size.
        # CLAMPED, BECAUSE A TITLE IS ALLOWED TO WRAP AND NOT ALLOWED TO
        # TAKE THE PAGE. At a 340px pane width a real subject ran to seven
        # lines and pushed the attribution, the actions and the message
        # itself so far down that the header became the page. Three lines
        # is enough for any subject worth reading; the rest is in the
        # tooltip. The character cap in _clamp_subject is the other half -
        # that one bounds hostile input, this one bounds the layout.
        self._subject = ClampedLabel("", max_lines=3)
        self._subject.setFont(t.make_font("dialog_heading"))
        t.role(self._subject, "primary")
        head_col.addWidget(self._subject)

        # ---- attribution: avatar, name, and ONE metadata line
        who = QHBoxLayout()
        who.setSpacing(t.SPACE_MD)
        self._avatar = _HeaderAvatar()
        who.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignTop)

        identity = QVBoxLayout()
        identity.setSpacing(1)
        # ELIDING, NOT WRAPPING. A 59-character display name ran under the
        # timestamp beside it and collided with it outright once the pane
        # got narrower. Wrapping is the other answer and it is wrong here:
        # a name is one thing, and letting it take three lines would push
        # the subject, the actions and the message itself down the page,
        # so the reading pane's layout would depend on how long somebody's
        # name happens to be. The full name stays in the tooltip.
        self._sender_name = ElidingLabel("")
        self._sender_name.setFont(t.make_font("sender"))
        t.role(self._sender_name, "primary")
        identity.addWidget(self._sender_name)

        # One line, assembled once, so an address cannot appear twice
        # because two builders each happened to include it.
        # Two lines: an address plus a recipient plus the receiving
        # account is a lot of text for a line nobody reads twice, and at a
        # narrow width a single long address alone wrapped to three.
        self._meta = ClampedLabel("", max_lines=2)
        self._meta.setFont(t.make_font("caption"))
        t.role(self._meta, "tertiary")
        identity.addWidget(self._meta)
        who.addLayout(identity, stretch=1)

        # The timestamp is a value, so it is set in the mono face and
        # right-aligned into its own column - it is the one piece of header
        # metadata people scan for rather than read.
        self._time = QLabel("")
        self._time.setFont(t.make_font("timestamp"))
        t.role(self._time, "tertiary")
        who.addWidget(self._time, 0, Qt.AlignmentFlag.AlignTop)
        head_col.addLayout(who)

        # ---- attachments
        self._attachment_list = QVBoxLayout()
        self._attachment_list.setSpacing(t.SPACE_XS)
        self._attachment_list.setContentsMargins(0, 0, 0, 0)
        head_col.addLayout(self._attachment_list)

        self._attachment_chip = self._make_chip(
            "attachment", "Has attachment", "secondary"
        )
        self._attachment_chip.setVisible(False)
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.addWidget(self._attachment_chip)
        chip_row.addStretch(1)
        head_col.addLayout(chip_row)

        page_col.addWidget(header)

        # ---------------------------------------------------------- actions
        self._actions = QWidget()
        self._actions.setObjectName("previewActions")
        act = QHBoxLayout(self._actions)
        act.setContentsMargins(
            _PAGE_INSET - t.SPACE_XS, t.SPACE_XS, _PAGE_INSET - t.SPACE_XS,
            t.SPACE_XS,
        )
        act.setSpacing(t.SPACE_XXS)

        # WHAT TO SEND NEXT, on the left where the eye lands after the
        # header. Reply is first because it is what the overwhelming
        # majority of these clicks are.
        self.reply_btn = IconButton("reply", "Reply")
        self.reply_btn.clicked.connect(self.reply_clicked.emit)
        self.reply_all_btn = IconButton("reply_all", "Reply to all")
        self.reply_all_btn.clicked.connect(self.reply_all_clicked.emit)
        self.forward_btn = IconButton("forward", "Forward")
        self.forward_btn.clicked.connect(self.forward_clicked.emit)
        for b in (self.reply_btn, self.reply_all_btn, self.forward_btn):
            act.addWidget(b)

        act.addStretch(1)

        # WHAT TO DO WITH THIS ONE, on the right. Delete is last and
        # furthest from Reply, so the destructive action is never adjacent
        # to the one people press without looking.
        self.star_btn = IconButton("star_outline", "Star", checkable=True)
        # The glyph carries the state (outline -> filled, ink -> amber), so
        # the checked SURFACE is switched off - see the note in style.py.
        self.star_btn.setProperty("toggles-glyph", "true")
        self.star_btn.clicked.connect(self.star_clicked.emit)
        self.unread_btn = IconButton("mark_unread", "Mark as unread")
        self.unread_btn.clicked.connect(self.mark_unread_clicked.emit)
        self.delete_btn = IconButton("trash", "Delete")
        self.delete_btn.clicked.connect(self.delete_clicked.emit)
        for b in (self.star_btn, self.unread_btn, self.delete_btn):
            act.addWidget(b)

        page_col.addWidget(self._actions)
        page_col.addWidget(Rule())

        # ------------------------------------------------- privacy notice
        # Remote images are withheld until asked for, so the reader is told
        # plainly rather than left wondering why a newsletter looks empty.
        self._images_bar = QWidget()
        self._images_bar.setObjectName("blockedImagesBar")
        bar_row = QHBoxLayout(self._images_bar)
        bar_row.setContentsMargins(t.SPACE_MD, t.SPACE_XS + 2, t.SPACE_SM,
                                   t.SPACE_XS + 2)
        bar_row.setSpacing(t.SPACE_SM)
        self._bar_icon = QLabel()
        self._bar_icon.setPixmap(simple_icon("shield", 14, t.WARNING).pixmap(14, 14))
        bar_row.addWidget(self._bar_icon)
        self._images_label = QLabel("Remote images blocked to protect your privacy")
        self._images_label.setFont(t.make_font("caption"))
        t.role(self._images_label, "secondary")
        bar_row.addWidget(self._images_label, stretch=1)
        self._show_images_btn = IconButton("check", "Load the blocked images")
        self._show_images_btn.clicked.connect(self._on_show_images)
        bar_row.addWidget(self._show_images_btn)
        self._images_bar.setVisible(False)

        bar_holder = QWidget()
        bar_holder_row = QVBoxLayout(bar_holder)
        bar_holder_row.setContentsMargins(
            _PAGE_INSET, t.SPACE_SM, _PAGE_INSET, 0
        )
        bar_holder_row.setSpacing(0)
        bar_holder_row.addWidget(self._images_bar)
        page_col.addWidget(bar_holder)

        # ------------------------------------------------------------ body
        # NO CARD, NO SHADOW, NO BORDER. The message sits directly on the
        # app floor; html_view caps the measure at ~72 characters. A
        # graphics effect here would also be the one effect the widget is
        # allowed - and motion.cross_fade needs that slot.
        self.body = HtmlMailView()
        self.body.setObjectName("emailBody")
        self.body.remote_images_blocked.connect(self._on_remote_images_blocked)
        page_col.addWidget(self.body, stretch=1)

        self._stack.addWidget(message_page)
        self.set_starred(False)
        self.set_actions_enabled(False)
        self._stack.setCurrentWidget(self._empty)

    # ------------------------------------------------------------- helpers

    def _make_chip(self, icon_name: str, text: str, role: str) -> QWidget:
        chip = QWidget()
        chip.setObjectName("attachmentChip")
        row = QHBoxLayout(chip)
        row.setContentsMargins(t.SPACE_SM + 2, t.SPACE_XS, t.SPACE_MD, t.SPACE_XS)
        row.setSpacing(t.SPACE_XS + 2)
        icon = QLabel()
        colour = {
            "danger": t.ERROR, "warning": t.WARNING,
        }.get(role, t.TEXT_SECONDARY)
        icon.setPixmap(simple_icon(icon_name, t.ICON_SIZE_ROW, colour)
                       .pixmap(t.ICON_SIZE_ROW, t.ICON_SIZE_ROW))
        row.addWidget(icon)
        label = QLabel(text)
        label.setFont(t.make_font("caption"))
        label.setTextFormat(Qt.TextFormat.PlainText)
        t.role(label, role)
        row.addWidget(label)
        return chip

    def retheme(self) -> None:
        """Re-tint the icons this pane holds.

        Text colour follows the stylesheet (theme.role), but an icon is a
        pixmap tinted with a specific colour when it was built, so the
        palette moving underneath it is invisible to it. Found by
        theme.retheme_tree.
        """
        self.set_starred(self.star_btn.isChecked())
        for button, name in (
            (self.reply_btn, "reply"), (self.reply_all_btn, "reply_all"),
            (self.forward_btn, "forward"), (self.unread_btn, "mark_unread"),
            (self.delete_btn, "trash"), (self._show_images_btn, "check"),
        ):
            button.set_icon(name)
        self._bar_icon.setPixmap(
            simple_icon("shield", 14, t.WARNING).pixmap(14, 14)
        )

    # ------------------------------------------------------------------ api

    def show_placeholder(self, title: str, body_text: str = "") -> None:
        self._empty.set_text(title, body_text)
        self._stack.setCurrentWidget(self._empty)
        self.set_actions_enabled(False)

    def show_nothing(self) -> None:
        """A blank reading pane, with no text at all."""
        self._empty.set_silent(True)
        self._stack.setCurrentWidget(self._empty)
        self.set_actions_enabled(False)

    def reset(self) -> None:
        """Back to the default "nothing selected" state."""
        self.show_placeholder(
            "Select a message", "Pick one from the list to read it here."
        )

    def show_message(
        self, *, subject: str, sender_name: str, sender_email: str,
        recipients: str, account_email: str, time_text: str,
        has_attachments: bool, is_starred: bool,
    ) -> None:
        # A new message: image consent starts fresh (see
        # HtmlMailView.set_email_html), so the bar starts hidden too.
        self._images_bar.setVisible(False)
        display_name = sender_name or sender_email or "(unknown sender)"

        def apply() -> None:
            self._subject.setText(_clamp_subject(subject))
            self._sender_name.setText(display_name)
            self._meta.setText(
                self._build_meta(display_name, sender_email, recipients,
                                 account_email)
            )
            self._time.setText(time_text)
            self._avatar.set_identity(sender_name, sender_email)
            self._attachment_chip.setVisible(has_attachments)
            self.set_actions_enabled(True)
            self.set_starred(is_starred)
            self._stack.setCurrentIndex(1)

        if self._stack.currentIndex() == 1:
            # Already reading something: change what this surface holds
            # rather than cutting to a different page.
            motion.cross_fade(self._stack, apply)
        else:
            apply()
            motion.fade_in(self._stack)

    @staticmethod
    def _build_meta(display_name: str, sender_email: str, recipients: str,
                    account_email: str) -> str:
        """One attribution line, assembled once.

        The address used to be emitted by two different builders - once
        under the name, once beside the timestamp - so most messages showed
        it twice. Here each fact is added at most once, and only when it
        adds something the name did not already say.
        """
        parts: list[str] = []
        if sender_email and sender_email != display_name:
            parts.append(sender_email)
        if recipients:
            parts.append(f"to {recipients}")
        if account_email and account_email not in parts:
            parts.append(f"via {account_email}")
        return "   ".join(parts)

    def set_actions_enabled(self, enabled: bool) -> None:
        for button in (self.reply_btn, self.reply_all_btn, self.forward_btn,
                       self.star_btn, self.unread_btn, self.delete_btn):
            button.setEnabled(enabled)

    def set_starred(self, starred: bool) -> None:
        self.star_btn.setChecked(starred)
        self.star_btn.setToolTip("Remove star" if starred else "Star")
        self.star_btn.setAccessibleName(self.star_btn.toolTip())
        # Starred is the one place in this pane hue is spent, and it is
        # spent because a star means something rather than decorating.
        self.star_btn.set_icon(
            "star_filled" if starred else "star_outline",
            colour=t.STARRED if starred else None,
        )

    def set_attachment_visible(self, visible: bool) -> None:
        self._attachment_chip.setVisible(visible)

    # -------------------------------------------------------- attachments

    def set_attachments(self, attachments: list[dict]) -> None:
        """One chip per attachment, coloured by the guard's verdict.

        A blocked attachment is shown with its reason rather than hidden -
        silently dropping it would leave the reader wondering where the
        file went - and the name shown is always the guard's sanitized
        form, never the raw one from the message.
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
            role = {"block": "danger", "warn": "warning"}.get(verdict, "secondary")
            icon_name = "warning" if role != "secondary" else "attachment"

            chip = self._make_chip(
                icon_name, _format_attachment_label(att), role
            )
            reason = att.get("reason") or ""
            if reason:
                chip.setToolTip(
                    ("Blocked: " if verdict == "block" else "Caution: ") + reason
                )
            holder = QWidget()
            wrapper = QHBoxLayout(holder)
            wrapper.setContentsMargins(0, 0, 0, 0)
            wrapper.addWidget(chip)
            wrapper.addStretch(1)
            self._attachment_list.addWidget(holder)

    # ------------------------------------------------------ remote images

    def _on_remote_images_blocked(self, count: int) -> None:
        plural = "s" if count != 1 else ""
        self._images_label.setText(
            f"{count} remote image{plural} blocked to protect your privacy"
        )
        motion.fade_in(self._images_bar)

    def _on_show_images(self) -> None:
        self.body.set_remote_images_allowed(True)
        motion.fade_out(self._images_bar)

"""Compose.

Treated as a major surface rather than a form. The whole window is one
uninterrupted writing space: a header strip with the account you are
sending from, borderless field rows separated by hairlines, and then the
body, which gets every remaining pixel.

Choices that came out of the redesign:

* Field rows have no boxes. A stack of bordered `QLineEdit`s reads as a
  database form; a label, a rule, and text reads as a letter. The rules
  are what keep it legible without the boxes.
* Cc and Bcc are hidden until asked for - they are needed on a minority
  of messages, and showing them always makes every message look like a
  broadcast. The toggle sits inline on the To row where it is looked for.
* Validation is inline and immediate: a bad address marks its own field
  and explains itself in the footer. The previous design raised a modal
  `QMessageBox` for "you forgot a recipient", which is a dialog on top of
  a dialog to say something the field could say itself.
* Discarding a message with content asks first; discarding an untouched
  window doesn't. A confirmation that fires on an empty form trains
  people to dismiss confirmations.
* `prefill` powers Reply / Reply all / Forward from the reading pane -
  quoting the original the way every mail client does, with the cursor
  placed above the quote rather than at the bottom of it.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.email import smtp_client
from app.email.gmail_client import GmailClient
from app.email.imap_client import ImapClient
from app.ui import theme as t
from app.ui.design import motion
from app.ui.components.buttons import AccentButton, Button, IconButton
from app.ui.components.dialog import confirm, divider, report_error
from app.ui.components.dropdown import Dropdown
from app.ui.native_theme import apply_dark_titlebar

log = logging.getLogger(__name__)

# Deliberately permissive: this catches "typed nothing sensible", not
# every RFC 5322 subtlety. Rejecting a valid-but-unusual address is a
# worse failure than letting the server reject a bad one.
_ADDRESS_RE = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")

_LABEL_WIDTH = 64


def parse_addresses(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def invalid_addresses(value: str) -> list[str]:
    return [a for a in parse_addresses(value) if not _ADDRESS_RE.match(a)]


def quote_body(sender: str, when: int, body: str) -> str:
    """The standard attribution line plus a '>' quoted body."""
    stamp = datetime.fromtimestamp(when).strftime("%d %b %Y at %H:%M") if when else ""
    header = f"On {stamp}, {sender} wrote:" if stamp else f"{sender} wrote:"
    quoted = "\n".join(f"> {line}" for line in (body or "").splitlines())
    return f"\n\n{header}\n{quoted}\n"


def reply_subject(subject: str) -> str:
    subject = subject or ""
    return subject if subject.lower().startswith("re:") else f"Re: {subject}".strip()


def forward_subject(subject: str) -> str:
    subject = subject or ""
    return subject if subject.lower().startswith("fwd:") else f"Fwd: {subject}".strip()


class _FieldRow(QWidget):
    """Label, hairline, borderless input - the compose row."""

    def __init__(self, label_text: str, field: QWidget, trailing: QWidget | None = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("composeFieldRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SPACE_LG)

        label = QLabel(label_text)
        label.setFont(t.make_font("field_label"))
        label.setProperty("tone", "tertiary")
        label.setFixedWidth(_LABEL_WIDTH)
        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(field, stretch=1)
        if trailing is not None:
            layout.addWidget(trailing, alignment=Qt.AlignmentFlag.AlignVCenter)


class _SendWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, account: dict, to: str, subject: str, body: str,
                 cc: str = "", bcc: str = "", parent=None):
        super().__init__(parent)
        self.account = account
        self.to = to
        self.subject = subject
        self.body = body
        self.cc = cc
        self.bcc = bcc

    def run(self) -> None:
        try:
            if self.account["provider"] == "gmail":
                GmailClient(self.account["email"]).send(
                    self.to, self.subject, self.body, self.cc, self.bcc
                )
            else:
                mime_bytes = smtp_client.send_message(
                    self.account, self.to, self.subject, self.body,
                    self.cc, self.bcc,
                )
                # Best effort: also file a copy into the IMAP Sent folder.
                try:
                    imap = ImapClient(self.account)
                    imap.append_to_sent(mime_bytes)
                    imap.close()
                except Exception as e:
                    log.info("Could not append sent copy: %s", e)
            self.succeeded.emit()
        except Exception as e:
            log.error("Send failed: %s", e)
            self.failed.emit(str(e))


class ComposeDialog(QDialog):
    sent = Signal()

    def __init__(self, accounts: list[dict], parent=None, prefill: dict | None = None):
        super().__init__(parent)
        self.accounts = accounts
        self._worker: _SendWorker | None = None
        self._extras_shown = False

        self.setWindowTitle("New message")
        self.setMinimumSize(660, 520)
        self.setObjectName("composeDialog")
        self.setModal(False)  # writing must not block reading the mailbox
        apply_dark_titlebar(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        outer.addWidget(divider())
        outer.addWidget(self._build_fields())
        outer.addWidget(divider())
        outer.addWidget(self._build_body(), stretch=1)
        outer.addWidget(divider())
        outer.addWidget(self._build_footer())

        if prefill:
            self.apply_prefill(prefill)
        self.to_edit.setFocus()

    # ------------------------------------------------------------- build

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("readerHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(t.SPACE_2XL, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        row.setSpacing(t.SPACE_MD)

        self._title = QLabel("New message")
        self._title.setFont(t.make_font("heading"))
        row.addWidget(self._title)
        row.addStretch(1)

        close = IconButton("close", "Discard this message (Esc)", size="sm")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        return header

    def _build_fields(self) -> QWidget:
        fields = QWidget()
        column = QVBoxLayout(fields)
        column.setContentsMargins(t.SPACE_2XL, t.SPACE_XS, t.SPACE_2XL, t.SPACE_XS)
        column.setSpacing(0)

        self.from_dropdown = Dropdown(
            [(a["email"], a) for a in self.accounts],
            current=self.accounts[0] if self.accounts else None,
        )
        column.addWidget(_FieldRow("From", self.from_dropdown))

        self.to_edit = self._address_field("name@example.com")
        self.extras_button = Button(
            "Cc / Bcc", variant="link", size="sm",
            tooltip="Add carbon-copy recipients",
        )
        self.extras_button.clicked.connect(self._toggle_extras)
        column.addWidget(_FieldRow("To", self.to_edit, self.extras_button))

        self.cc_edit = self._address_field("Carbon copy")
        self._cc_row = _FieldRow("Cc", self.cc_edit)
        self._cc_row.setVisible(False)
        column.addWidget(self._cc_row)

        self.bcc_edit = self._address_field("Blind carbon copy")
        self._bcc_row = _FieldRow("Bcc", self.bcc_edit)
        self._bcc_row.setVisible(False)
        column.addWidget(self._bcc_row)

        self.subject_edit = QLineEdit()
        self.subject_edit.setObjectName("composeField")
        self.subject_edit.setPlaceholderText("Subject")
        self.subject_edit.setFont(t.make_font("body_strong"))
        subject_row = _FieldRow("Subject", self.subject_edit)
        subject_row.setProperty("last", True)
        column.addWidget(subject_row)
        return fields

    def _address_field(self, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName("composeField")
        field.setPlaceholderText(placeholder)
        field.setFont(t.make_font("field_value"))
        field.textChanged.connect(lambda _=None, f=field: self._clear_invalid(f))
        return field

    def _build_body(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(t.SPACE_2XL, t.SPACE_XL, t.SPACE_2XL, t.SPACE_XL)
        self.body_edit = QPlainTextEdit()
        self.body_edit.setObjectName("composeBody")
        self.body_edit.setFont(t.make_font("body"))
        self.body_edit.setPlaceholderText("Write your message")
        self.body_edit.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        layout.addWidget(self.body_edit)
        return wrapper

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("readerFooter")
        row = QHBoxLayout(footer)
        row.setContentsMargins(t.SPACE_2XL, t.SPACE_LG, t.SPACE_2XL, t.SPACE_LG)
        row.setSpacing(t.SPACE_MD)

        self.send_btn = AccentButton("Send", icon="paper")
        self.send_btn.setIconSize(QSize(t.ICON_SM, t.ICON_SM))
        self.send_btn.setDefault(True)
        self.send_btn.setToolTip("Send this message (Ctrl+Enter)")
        self.send_btn.clicked.connect(self._on_send)
        row.addWidget(self.send_btn)

        self.status_label = QLabel("")
        self.status_label.setFont(t.make_font("status"))
        self.status_label.setProperty("tone", "secondary")
        self.status_label.setWordWrap(True)
        row.addWidget(self.status_label, stretch=1)

        discard = Button("Discard", variant="subtle", tooltip="Discard (Esc)")
        discard.clicked.connect(self.reject)
        row.addWidget(discard)
        return footer

    # ----------------------------------------------------------- prefill

    def apply_prefill(self, prefill: dict) -> None:
        """Fill the form for a reply/reply-all/forward."""
        self._title.setText(prefill.get("title", "New message"))
        self.setWindowTitle(prefill.get("title", "New message"))
        self.to_edit.setText(prefill.get("to", ""))
        cc = prefill.get("cc", "")
        if cc:
            self._toggle_extras(force=True)
            self.cc_edit.setText(cc)
        self.subject_edit.setText(prefill.get("subject", ""))
        body = prefill.get("body", "")
        self.body_edit.setPlainText(body)
        # Cursor above the quote, which is where a reply is written.
        self.body_edit.moveCursor(self.body_edit.textCursor().MoveOperation.Start)
        account = prefill.get("account")
        if account is not None:
            for _label, value in self.from_dropdown._items:
                if value.get("id") == account.get("id"):
                    self.from_dropdown.set_value(value, emit=False)
                    break
        if prefill.get("focus") == "body":
            self.body_edit.setFocus()

    def _toggle_extras(self, force: bool = False) -> None:
        self._extras_shown = True if force else not self._extras_shown
        self._cc_row.setVisible(self._extras_shown)
        self._bcc_row.setVisible(self._extras_shown)
        self.extras_button.setVisible(not self._extras_shown)
        if self._extras_shown and not force:
            self.cc_edit.setFocus()

    # ------------------------------------------------------------- state

    def has_content(self) -> bool:
        return bool(
            self.to_edit.text().strip()
            or self.subject_edit.text().strip()
            or self.body_edit.toPlainText().strip()
        )

    def _set_status(self, text: str, *, tone: str = "secondary") -> None:
        t.set_variant(self.status_label, "tone", tone)
        self.status_label.setText(text)

    def _mark_invalid(self, field: QLineEdit, message: str) -> None:
        t.set_variant(field, "invalid", "true")
        self._set_status(message, tone="danger")
        field.setFocus()
        # A shake says "this one" faster than reading the footer does.
        row = field.parentWidget() or field
        origin = row.pos()
        motion.shake(
            row, lambda dx: row.move(origin.x() + int(dx), origin.y())
        )

    @staticmethod
    def _clear_invalid(field: QLineEdit) -> None:
        if field.property("invalid"):
            t.set_variant(field, "invalid", None)

    # -------------------------------------------------------------- send

    def _validate(self) -> bool:
        to = self.to_edit.text().strip()
        if not to:
            self._mark_invalid(self.to_edit, "Add at least one recipient.")
            return False
        for field, label in (
            (self.to_edit, "To"), (self.cc_edit, "Cc"), (self.bcc_edit, "Bcc"),
        ):
            bad = invalid_addresses(field.text())
            if bad:
                self._mark_invalid(
                    field,
                    f"{label}: {bad[0]} does not look like an email address.",
                )
                return False
        return True

    def _on_send(self) -> None:
        account = self.from_dropdown.value()
        if not account:
            self._set_status("Add an email account first.", tone="danger")
            return
        if not self._validate():
            return
        if not self.subject_edit.text().strip() and not confirm(
            self, "Send without a subject?",
            "This message has no subject line. Send it anyway?",
            confirm_text="Send", cancel_text="Go back",
        ):
            self.subject_edit.setFocus()
            return

        self.send_btn.setEnabled(False)
        self._set_status("Sending...")
        self._worker = _SendWorker(
            account, self.to_edit.text().strip(), self.subject_edit.text().strip(),
            self.body_edit.toPlainText(), self.cc_edit.text().strip(),
            self.bcc_edit.text().strip(), self,
        )
        self._worker.succeeded.connect(self._on_sent)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_sent(self) -> None:
        self.sent.emit()
        self.accept()

    def _on_failed(self, message: str) -> None:
        self.send_btn.setEnabled(True)
        self._set_status("Not sent.", tone="danger")
        report_error(
            self, "Could not send this message",
            "Your message was not sent, and nothing has been lost - the "
            "window is still open so you can try again.",
            detail=message,
        )

    # -------------------------------------------------------- shortcuts

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._on_send()
            event.accept()
            return
        super().keyPressEvent(event)

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return  # never discard mid-send
        if self.has_content() and not confirm(
            self, "Discard this message?",
            "The message has not been sent. Discarding it cannot be undone.",
            confirm_text="Discard", cancel_text="Keep writing", destructive=True,
        ):
            return
        super().reject()

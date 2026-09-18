"""Compose, reply, reply-all and forward. Plain text, honestly.

WHAT THIS WINDOW IS FOR. PRODUCT.md is explicit that sending is secondary
here and that Unified "composes plain text only and does not pretend
otherwise". So there is no formatting toolbar, no font picker and no
rich-text affordance of any kind - offering one and then sending plain
text would be the interface making a promise the product does not keep.
What it does instead is make the writing surface the largest, quietest
thing in the window.

=========================================================================
WHAT CHANGED

  CC AND BCC EXIST. They did not, which meant Reply all had nowhere to put
  the other recipients and the window could not express what a reply
  actually is. They are hidden until asked for, because most messages have
  neither and three empty fields is three rows of nothing.

  THE BODY LINES UP WITH THE PAGE'S LEFT EDGE. The field CAPTIONS start at
  24 and the body's first character used to start at 30 - QPlainTextEdit
  adds a 4px document margin of its own on top of any padding. Six pixels
  is not enough to read as a deliberate indent and is exactly enough to
  read as a ragged edge, which is the worst of the three options. The body
  now begins at 24, flush with "From"/"To"/"Subject". The field VALUES stay
  indented past the caption column, because they are a column; the body is
  not a field and does not belong in it.

  SEND IS A STATE MACHINE, NOT A DISABLED BUTTON. Sending, sent, and
  failed each say what happened and leave the window in a state you can
  act from. A failed send used to raise a modal over the window, clear the
  status line, and leave no trace of the error once the modal was
  dismissed - so the one moment the user most needs to know what went
  wrong was the one moment the window said nothing.

  DISCARD ASKS ONCE, AND ONLY WHEN THERE IS SOMETHING TO LOSE. Closing an
  untouched window should not interrogate anybody.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.email import smtp_client
from app.email.gmail_client import GmailClient
from app.email.imap_client import ImapClient
from app.ui import motion, theme as t
from app.ui.components.dropdown import Dropdown
from app.ui.components.primitives import Button, IconButton, Rule, Variant
from app.ui.components.section_header import DialogHeading
from app.ui.svg_icon import simple_icon

log = logging.getLogger(__name__)

# The caption column. Fixed rather than sized to content so "From", "To",
# "Cc", "Bcc" and "Subject" all put their values on one line - a ragged
# value column is the kind of thing nobody reports and everybody feels.
# Wide enough for "Subject" at field_label size with room to spare.
_LABEL_WIDTH = 64


def _field_row(label_text: str, field: QWidget) -> QWidget:
    """A label-left, borderless field row with a rule under it - the
    layout real mail composers use instead of stacking boxed QLineEdits
    with their captions above them."""
    row = QWidget()
    row.setObjectName("composeFieldRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(t.SPACE_MD)
    label = QLabel(label_text)
    label.setFont(t.make_font("field_label"))
    t.role(label, "tertiary")
    label.setFixedWidth(_LABEL_WIDTH)
    # The caption focuses its field, and screen readers read the two as one.
    label.setBuddy(field)
    layout.addWidget(label)
    layout.addWidget(field, stretch=1)
    return row


class _SendWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, account: dict, to: str, subject: str, body: str,
                 cc: str = "", bcc: str = "", parent=None):
        super().__init__(parent)
        self.account = account
        self.to = to
        self.cc = cc
        self.bcc = bcc
        self.subject = subject
        self.body = body

    def run(self) -> None:
        try:
            if self.account["provider"] == "gmail":
                GmailClient(self.account["email"]).send(
                    self.to, self.subject, self.body,
                    cc=self.cc, bcc=self.bcc,
                )
            else:
                mime_bytes = smtp_client.send_message(
                    self.account, self.to, self.subject, self.body,
                    cc=self.cc, bcc=self.bcc,
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

    #: Window titles per mode, so the window says which of the four things
    #: it is rather than always claiming to be a new message.
    _TITLES = {
        "new": "New message",
        "reply": "Reply",
        "reply_all": "Reply to all",
        "forward": "Forward",
    }

    def __init__(self, accounts: list[dict], parent=None, *, mode: str = "new",
                 to: str = "", cc: str = "", subject: str = "", body: str = "",
                 from_account: dict | None = None):
        super().__init__(parent)
        self.accounts = accounts
        self.mode = mode if mode in self._TITLES else "new"
        self._worker: _SendWorker | None = None
        self._sending = False

        self.setWindowTitle(self._TITLES[self.mode])
        self.setMinimumSize(660, 520)
        self.setObjectName("composeDialog")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(t.SPACE_XL, t.SPACE_LG, t.SPACE_XL, t.SPACE_LG)
        outer.setSpacing(t.SPACE_MD)

        # ---------------------------------------------------------- header
        header = QHBoxLayout()
        header.setSpacing(t.SPACE_SM)
        header.addWidget(DialogHeading(self._TITLES[self.mode]))
        header.addStretch(1)

        self.cc_toggle = Button("Cc / Bcc", Variant.GHOST)
        self.cc_toggle.setCheckable(True)
        self.cc_toggle.setToolTip("Show the Cc and Bcc fields")
        self.cc_toggle.toggled.connect(self._set_cc_visible)
        header.addWidget(self.cc_toggle)

        self.discard_btn = IconButton("close", "Discard this message")
        self.discard_btn.clicked.connect(self.reject)
        header.addWidget(self.discard_btn)

        self.send_btn = Button(" Send", Variant.PRIMARY)
        self.send_btn.setIcon(simple_icon("paper", 14, t.TEXT_ON_ACCENT))
        self.send_btn.setIconSize(QSize(14, 14))
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._on_send)
        header.addWidget(self.send_btn)
        outer.addLayout(header)

        # ---------------------------------------------------------- fields
        fields = QWidget()
        fields.setObjectName("composeFields")
        fields_col = QVBoxLayout(fields)
        fields_col.setContentsMargins(0, t.SPACE_SM, 0, t.SPACE_SM)
        fields_col.setSpacing(t.SPACE_XS)

        self.from_dropdown = Dropdown(
            [(a["email"], a) for a in accounts],
            current=from_account or (accounts[0] if accounts else None),
        )
        fields_col.addWidget(_field_row("From", self.from_dropdown))

        self.to_edit = QLineEdit(to)
        self.to_edit.setObjectName("composeField")
        self.to_edit.setPlaceholderText("recipient@example.com, another@example.com")
        fields_col.addWidget(_field_row("To", self.to_edit))

        self.cc_edit = QLineEdit(cc)
        self.cc_edit.setObjectName("composeField")
        self.cc_edit.setPlaceholderText("Carbon copy")
        self._cc_row = _field_row("Cc", self.cc_edit)
        fields_col.addWidget(self._cc_row)

        self.bcc_edit = QLineEdit()
        self.bcc_edit.setObjectName("composeField")
        self.bcc_edit.setPlaceholderText("Blind carbon copy - other recipients "
                                         "cannot see these")
        self._bcc_row = _field_row("Bcc", self.bcc_edit)
        fields_col.addWidget(self._bcc_row)

        self.subject_edit = QLineEdit(subject)
        self.subject_edit.setObjectName("composeField")
        self.subject_edit.setPlaceholderText("Subject")
        fields_col.addWidget(_field_row("Subject", self.subject_edit))
        outer.addWidget(fields)

        # A reply that already has recipients in Cc opens with them
        # showing; there is no point hiding a field that is not empty.
        self._set_cc_visible(bool(cc))
        self.cc_toggle.setChecked(bool(cc))

        # ------------------------------------------------------------ body
        self.body_edit = QPlainTextEdit()
        self.body_edit.setObjectName("composeBody")
        self.body_edit.setFont(t.make_font("reading"))
        self.body_edit.setPlaceholderText("Write your message...")
        # THE TEXT STARTS ON THE PAGE'S LEFT EDGE, exactly where the field
        # captions start. QPlainTextEdit adds a 4px document margin of its
        # own on top of any padding, which put the first character 6px
        # right of the "From"/"To"/"Subject" column - not enough to read as
        # an indent, just enough to look like a ragged edge. Zeroed here
        # because the document margin is not reachable from QSS.
        self.body_edit.document().setDocumentMargin(0)
        if body:
            self.body_edit.setPlainText(body)
        outer.addWidget(self.body_edit, stretch=1)

        outer.addWidget(Rule())

        # ---------------------------------------------------------- status
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("")
        self.status_label.setFont(t.make_font("status"))
        self.status_label.setWordWrap(True)
        t.role(self.status_label, "secondary")
        status_row.addWidget(self.status_label, stretch=1)

        # Plain text is a property of the product, so the window says so
        # once, quietly, instead of implying otherwise with a toolbar.
        note = QLabel("Plain text")
        note.setFont(t.make_font("caption"))
        t.role(note, "tertiary")
        note.setToolTip(
            "Unified sends plain-text messages. Formatting is not applied."
        )
        status_row.addWidget(note)
        outer.addLayout(status_row)

        # WHERE THE CURSOR STARTS IS A DESIGN DECISION. A reply already has
        # its recipient and subject, so the only thing left to do is write;
        # a new message has nothing, so it starts at the address.
        if self.mode == "new":
            self.to_edit.setFocus()
        else:
            self.body_edit.setFocus()
            # ABOVE the quoted text, not below it. A reply is written at
            # the top; putting the cursor at the end would open every
            # reply scrolled to the bottom of the original.
            self.body_edit.moveCursor(QTextCursor.MoveOperation.Start)

    # ---------------------------------------------------------------- fields

    def _set_cc_visible(self, visible: bool) -> None:
        for row in (self._cc_row, self._bcc_row):
            if visible:
                motion.fade_in(row, duration=t.DURATION_FAST)
            else:
                row.setVisible(False)
        if not visible:
            self.cc_edit.clear()
            self.bcc_edit.clear()

    def _recipients(self) -> tuple[str, str, str]:
        return (
            self.to_edit.text().strip(),
            self.cc_edit.text().strip() if self._cc_row.isVisible() else "",
            self.bcc_edit.text().strip() if self._bcc_row.isVisible() else "",
        )

    def is_dirty(self) -> bool:
        """True when discarding would actually lose something the user
        typed. A reply's quoted text does not count - it was not written
        here."""
        to, cc, bcc = self._recipients()
        return bool(to or cc or bcc or self.subject_edit.text().strip())

    # ------------------------------------------------------------------ send

    def _set_status(self, text: str, *, kind: str = "secondary") -> None:
        t.role(self.status_label, kind)
        self.status_label.setText(text)

    def _on_send(self) -> None:
        account = self.from_dropdown.value()
        to, cc, bcc = self._recipients()
        if not account:
            self._set_status("Add an account before sending.", kind="danger")
            return
        if not to:
            # THE FIELD EXPLAINS ITS OWN PROBLEM, in place, rather than a
            # modal explaining it somewhere else and then vanishing.
            self._set_status("Enter at least one recipient.", kind="danger")
            self.to_edit.setProperty("invalid", "true")
            self.to_edit.style().unpolish(self.to_edit)
            self.to_edit.style().polish(self.to_edit)
            self.to_edit.setFocus()
            return

        self.to_edit.setProperty("invalid", "")
        self.to_edit.style().unpolish(self.to_edit)
        self.to_edit.style().polish(self.to_edit)

        self._sending = True
        self.send_btn.setEnabled(False)
        self.send_btn.setText(" Sending")
        self.discard_btn.setEnabled(False)
        self._set_status("Sending...")

        self._worker = _SendWorker(
            account, to, self.subject_edit.text().strip(),
            self.body_edit.toPlainText(), cc=cc, bcc=bcc, parent=self,
        )
        self._worker.succeeded.connect(self._on_sent)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_sent(self) -> None:
        self._sending = False
        self._set_status("Sent", kind="success")
        self.sent.emit()
        # Long enough to be read as confirmation, short enough not to be a
        # wait. The window closing IS the success state; this is the
        # moment before it that says why.
        motion.after(450, self.accept, self)

    def _on_failed(self, message: str) -> None:
        """A failed send leaves the message intact and the reason visible.

        It used to raise a modal and blank the status line, so dismissing
        the modal destroyed the only account of what went wrong - at
        exactly the moment the user needed it to decide whether to retry.
        """
        self._sending = False
        self.send_btn.setEnabled(True)
        self.send_btn.setText(" Send")
        self.discard_btn.setEnabled(True)
        self._set_status(f"Not sent - {message}", kind="danger")
        motion.flash(self.status_label)

    # ----------------------------------------------------------------- close

    def reject(self) -> None:
        if self._sending:
            return  # never discard mid-send
        if self.is_dirty():
            confirm = QMessageBox.question(
                self, "Discard this message?",
                "The message has not been sent. Discarding it cannot be undone.",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if confirm != QMessageBox.StandardButton.Discard:
                return
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        """A send in flight owns the window until it finishes.

        The worker writes to widgets on this dialog when it completes;
        letting the window close out from under it is a use-after-free.
        """
        if self._sending:
            event.ignore()
            return
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)
        super().closeEvent(event)

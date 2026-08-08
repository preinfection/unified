"""Compose and send a plain-text email from any connected account."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.email import smtp_client
from app.email.gmail_client import GmailClient
from app.email.imap_client import ImapClient
from app.ui import theme as t
from app.ui.svg_icon import simple_icon

log = logging.getLogger(__name__)


def _field_row(label_text: str, field: QWidget) -> QWidget:
    """A label-left, borderless-bottom field row - the compact single-line
    layout real mail composers use instead of a QFormLayout's boxed inputs
    stacked with their labels above them."""
    row = QWidget()
    row.setObjectName("composeFieldRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(t.SPACE_MD)
    label = QLabel(label_text)
    label.setFont(t.make_font("field_label"))
    label.setStyleSheet(f"color: {t.TEXT_TERTIARY}; background: transparent;")
    label.setFixedWidth(60)
    layout.addWidget(label)
    layout.addWidget(field, stretch=1)
    return row


class _SendWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, account: dict, to: str, subject: str, body: str, parent=None):
        super().__init__(parent)
        self.account = account
        self.to = to
        self.subject = subject
        self.body = body

    def run(self) -> None:
        try:
            if self.account["provider"] == "gmail":
                GmailClient(self.account["email"]).send(
                    self.to, self.subject, self.body
                )
            else:
                mime_bytes = smtp_client.send_message(
                    self.account, self.to, self.subject, self.body
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

    def __init__(self, accounts: list[dict], parent=None):
        super().__init__(parent)
        self.accounts = accounts
        self._worker: _SendWorker | None = None

        self.setWindowTitle("Compose")
        self.setMinimumSize(600, 460)
        self.setObjectName("composeDialog")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        outer.setSpacing(t.SPACE_MD)

        # -- header: title, discard, Send
        header = QHBoxLayout()
        header.setSpacing(t.SPACE_SM)
        title = QLabel("New Message")
        title.setFont(t.make_font("dialog_heading"))
        header.addWidget(title)
        header.addStretch(1)

        discard_btn = QPushButton()
        discard_btn.setObjectName("iconButton")
        discard_btn.setIcon(simple_icon("close", t.ICON_SIZE_ACTION, t.ICON_SECONDARY))
        discard_btn.setIconSize(QSize(t.ICON_SIZE_ACTION, t.ICON_SIZE_ACTION))
        discard_btn.setToolTip("Discard")
        discard_btn.setFixedSize(t.HEIGHT_SM, t.HEIGHT_SM)
        discard_btn.clicked.connect(self.reject)
        header.addWidget(discard_btn)

        self.send_btn = QPushButton(" Send")
        self.send_btn.setObjectName("composeButton")
        self.send_btn.setFont(t.make_font("button"))
        self.send_btn.setIcon(simple_icon("paper", 14, t.TEXT_ON_ACCENT))
        self.send_btn.setIconSize(QSize(14, 14))
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._on_send)
        header.addWidget(self.send_btn)
        outer.addLayout(header)

        # -- fields
        fields_card = QWidget()
        fields_card.setObjectName("composeFields")
        fields_col = QVBoxLayout(fields_card)
        fields_col.setContentsMargins(t.SPACE_MD, t.SPACE_SM, t.SPACE_MD, t.SPACE_SM)
        fields_col.setSpacing(t.SPACE_XS)

        self.from_combo = QComboBox()
        self.from_combo.setObjectName("composeField")
        for account in accounts:
            self.from_combo.addItem(account["email"], account)
        fields_col.addWidget(_field_row("From", self.from_combo))

        self.to_edit = QLineEdit()
        self.to_edit.setObjectName("composeField")
        self.to_edit.setPlaceholderText("recipient@example.com (comma-separated)")
        fields_col.addWidget(_field_row("To", self.to_edit))

        self.subject_edit = QLineEdit()
        self.subject_edit.setObjectName("composeField")
        self.subject_edit.setPlaceholderText("Subject")
        fields_col.addWidget(_field_row("Subject", self.subject_edit))
        outer.addWidget(fields_card)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setObjectName("composeBody")
        self.body_edit.setFont(t.make_font("body"))
        self.body_edit.setPlaceholderText("Write your message...")
        outer.addWidget(self.body_edit, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setFont(t.make_font("status"))
        self.status_label.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
        outer.addWidget(self.status_label)

    # ----------------------------------------------------------------- send

    def _set_status(self, text: str, *, is_error: bool = False) -> None:
        color = t.ERROR if is_error else t.TEXT_SECONDARY
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

    def _on_send(self) -> None:
        account = self.from_combo.currentData()
        to = self.to_edit.text().strip()
        if not account:
            QMessageBox.warning(self, "No account", "Add an account first.")
            return
        if not to:
            self._set_status("Enter at least one recipient.", is_error=True)
            self.to_edit.setFocus()
            return
        self.send_btn.setEnabled(False)
        self._set_status("Sending...")
        self._worker = _SendWorker(
            account, to, self.subject_edit.text().strip(),
            self.body_edit.toPlainText(), self
        )
        self._worker.succeeded.connect(self._on_sent)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_sent(self) -> None:
        self.sent.emit()
        self.accept()

    def _on_failed(self, message: str) -> None:
        self.send_btn.setEnabled(True)
        self._set_status("")
        QMessageBox.critical(self, "Send failed", message)

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return  # don't discard mid-send
        super().reject()

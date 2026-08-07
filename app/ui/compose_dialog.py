"""Compose and send a plain-text email from any connected account."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from app.email import smtp_client
from app.email.gmail_client import GmailClient
from app.email.imap_client import ImapClient

log = logging.getLogger(__name__)


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
        self.setMinimumSize(560, 420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.from_combo = QComboBox()
        for account in accounts:
            self.from_combo.addItem(account["email"], account)
        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("recipient@example.com (comma-separated)")
        self.subject_edit = QLineEdit()
        form.addRow("From:", self.from_combo)
        form.addRow("To:", self.to_edit)
        form.addRow("Subject:", self.subject_edit)
        layout.addLayout(form)

        self.body_edit = QPlainTextEdit()
        layout.addWidget(self.body_edit, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("secondary")
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Send")
        self.buttons.accepted.connect(self._on_send)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _on_send(self) -> None:
        account = self.from_combo.currentData()
        to = self.to_edit.text().strip()
        if not account:
            QMessageBox.warning(self, "No account", "Add an account first.")
            return
        if not to:
            QMessageBox.warning(self, "Missing recipient", "Enter a recipient.")
            return
        self.buttons.setEnabled(False)
        self.status_label.setText("Sending...")
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
        self.buttons.setEnabled(True)
        self.status_label.setText("")
        QMessageBox.critical(self, "Send failed", message)

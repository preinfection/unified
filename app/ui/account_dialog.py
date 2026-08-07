"""Dialog for adding a Gmail (OAuth) or custom IMAP/SMTP account."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.auth import gmail_oauth
from app.services.account_manager import AccountError, AccountManager

log = logging.getLogger(__name__)


class _GmailAuthWorker(QThread):
    """Runs the blocking OAuth browser flow off the UI thread."""

    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, manager: AccountManager, parent=None):
        super().__init__(parent)
        self.manager = manager

    def run(self) -> None:
        try:
            account = self.manager.add_gmail_account()
            self.succeeded.emit(account)
        except (AccountError, gmail_oauth.GmailAuthError) as e:
            self.failed.emit(str(e))
        except Exception as e:
            log.exception("Gmail OAuth flow failed")
            self.failed.emit(f"Authentication failed: {e}")


class _ImapVerifyWorker(QThread):
    """Verifies IMAP login and stores the account off the UI thread."""

    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, manager: AccountManager, params: dict, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.params = params

    def run(self) -> None:
        try:
            account = self.manager.add_imap_account(**self.params)
            self.succeeded.emit(account)
        except Exception as e:
            self.failed.emit(str(e))


class AccountDialog(QDialog):
    """Returns the newly added account via self.added_account when accepted."""

    def __init__(self, manager: AccountManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.added_account: dict | None = None
        self._worker: QThread | None = None

        self.setWindowTitle("Add Account")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form_top = QFormLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Gmail (sign in with Google)", "Custom IMAP/SMTP"])
        form_top.addRow("Account type:", self.type_combo)
        layout.addLayout(form_top)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_gmail_page())
        self.stack.addWidget(self._build_imap_page())
        layout.addWidget(self.stack)
        self.type_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        self.status_label = QLabel("")
        self.status_label.setObjectName("secondary")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add Account")
        self.buttons.accepted.connect(self._on_add)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    # ------------------------------------------------------------------ pages

    def _build_gmail_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        text = QLabel(
            "Sign in with your Google account in the browser window that opens. "
            "No password is stored - only an OAuth token, kept in the Windows "
            "Credential Manager."
        )
        text.setWordWrap(True)
        v.addWidget(text)
        if not gmail_oauth.client_secrets_available():
            warn = QLabel(
                "A Google OAuth client file has not been configured yet. "
                "Open Settings and select your credentials.json first "
                "(Google Cloud Console > APIs & Services > Credentials > "
                "OAuth client ID, type 'Desktop app', with the Gmail API enabled)."
            )
            warn.setWordWrap(True)
            warn.setObjectName("secondary")
            v.addWidget(warn)
        return page

    def _build_imap_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.imap_email = QLineEdit()
        self.imap_email.setPlaceholderText("you@example.com")
        self.imap_password = QLineEdit()
        self.imap_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.imap_password.setPlaceholderText("Password or app password")
        self.imap_host = QLineEdit()
        self.imap_host.setPlaceholderText("imap.example.com")
        self.imap_port = QSpinBox()
        self.imap_port.setRange(1, 65535)
        self.imap_port.setValue(993)
        self.smtp_host = QLineEdit()
        self.smtp_host.setPlaceholderText("smtp.example.com")
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(587)
        form.addRow("Email address:", self.imap_email)
        form.addRow("Password:", self.imap_password)
        form.addRow("IMAP server:", self.imap_host)
        form.addRow("IMAP port:", self.imap_port)
        form.addRow("SMTP server:", self.smtp_host)
        form.addRow("SMTP port:", self.smtp_port)
        note = QLabel(
            "The password is stored only in the Windows Credential Manager, "
            "never in a file. For Gmail via IMAP, use an app password."
        )
        note.setWordWrap(True)
        note.setObjectName("secondary")
        form.addRow(note)
        return page

    # ----------------------------------------------------------------- actions

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.buttons.setEnabled(not busy)
        self.type_combo.setEnabled(not busy)
        self.stack.setEnabled(not busy)
        self.status_label.setText(message)

    def _on_add(self) -> None:
        if self.type_combo.currentIndex() == 0:
            if not gmail_oauth.client_secrets_available():
                QMessageBox.warning(
                    self,
                    "Missing OAuth client",
                    "Configure the Google credentials.json in Settings first.",
                )
                return
            self._set_busy(True, "Waiting for Google sign-in in your browser...")
            self._worker = _GmailAuthWorker(self.manager, self)
        else:
            email_addr = self.imap_email.text().strip()
            password = self.imap_password.text()
            host = self.imap_host.text().strip()
            if not email_addr or not password or not host:
                QMessageBox.warning(
                    self, "Missing details",
                    "Email, password and IMAP server are required."
                )
                return
            params = dict(
                email_addr=email_addr,
                password=password,
                imap_host=host,
                imap_port=self.imap_port.value(),
                smtp_host=self.smtp_host.text().strip() or host.replace("imap", "smtp"),
                smtp_port=self.smtp_port.value(),
            )
            self._set_busy(True, f"Verifying login at {host}...")
            self._worker = _ImapVerifyWorker(self.manager, params, self)

        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_success(self, account: dict) -> None:
        self.added_account = account
        self.accept()

    def _on_failure(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Could not add account", message)

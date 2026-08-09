"""Dialog for adding a Gmail (OAuth) or custom IMAP/SMTP account."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
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
from app.ui import theme as t
from app.ui.components.button import AccentButton
from app.ui.components.dropdown import Dropdown
from app.ui.components.section_header import DialogHeading, SectionHeader
from app.ui.svg_icon import simple_icon

log = logging.getLogger(__name__)


class _GmailAuthWorker(QThread):
    """Runs the blocking OAuth browser flow off the UI thread.

    cancel() may be called from the UI thread at any time; the flow's
    localhost callback server shuts down within its poll interval and the
    thread exits via the cancelled signal.
    """

    succeeded = Signal(dict)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, manager: AccountManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.flow = gmail_oauth.CancellableOAuthFlow(timeout_seconds=120)

    def cancel(self) -> None:
        self.flow.cancel()

    def run(self) -> None:
        try:
            creds = self.flow.run()
            account = self.manager.register_gmail_account(creds)
            self.succeeded.emit(account)
        except gmail_oauth.OAuthCancelled:
            self.cancelled.emit()
        except gmail_oauth.OAuthTimeout:
            self.failed.emit("Google sign-in timed out")
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
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        layout.setSpacing(t.SPACE_MD)

        layout.addWidget(DialogHeading("Add Account"))

        layout.addWidget(SectionHeader("Account type"))
        panel = QWidget()
        panel.setObjectName("settingsPanel")
        panel_col = QVBoxLayout(panel)
        panel_col.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        panel_col.setSpacing(t.SPACE_SM)

        type_row = QHBoxLayout()
        type_label = QLabel("Account type")
        type_label.setFont(t.make_font("field_label"))
        type_label.setStyleSheet(f"color: {t.TEXT_TERTIARY};")
        type_label.setFixedWidth(90)
        type_row.addWidget(type_label)
        self.type_dropdown = Dropdown(
            [("Gmail (sign in with Google)", 0), ("Custom IMAP/SMTP", 1)], current=0
        )
        type_row.addWidget(self.type_dropdown, stretch=1)
        panel_col.addLayout(type_row)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_gmail_page())
        self.stack.addWidget(self._build_imap_page())
        panel_col.addWidget(self.stack)
        self.type_dropdown.changed.connect(self.stack.setCurrentIndex)
        layout.addWidget(panel)

        self.status_label = QLabel("")
        self.status_label.setObjectName("secondary")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        self.cancel_btn = self.buttons.addButton(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.ok_btn = AccentButton(" Add Account")
        self.ok_btn.setIcon(simple_icon("check", 13, t.TEXT_ON_ACCENT))
        self.buttons.addButton(self.ok_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self._on_add)
        # rejected fires for the Cancel button and Esc; reject() is overridden
        # to turn it into "Cancel Login" while OAuth is running.
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._close_after_cancel = False

    # ------------------------------------------------------------------ pages

    def _build_gmail_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(t.SPACE_SM)
        text = QLabel(
            "Sign in with your Google account in the browser window that opens. "
            "No password is stored - only an OAuth token, kept in the Windows "
            "Credential Manager."
        )
        text.setFont(t.make_font("body"))
        text.setWordWrap(True)
        v.addWidget(text)
        if not gmail_oauth.client_secrets_available():
            warn_row = QHBoxLayout()
            warn_row.setSpacing(t.SPACE_XS + 2)
            warn_icon = QLabel()
            warn_icon.setPixmap(simple_icon("warning", 15, t.WARNING).pixmap(15, 15))
            warn_icon.setAlignment(Qt.AlignmentFlag.AlignTop)
            warn = QLabel(
                "A Google OAuth client file has not been configured yet. "
                "Open Settings and select your credentials.json first "
                "(Google Cloud Console > APIs & Services > Credentials > "
                "OAuth client ID, type 'Desktop app', with the Gmail API enabled)."
            )
            warn.setFont(t.make_font("body"))
            warn.setWordWrap(True)
            warn.setObjectName("secondary")
            warn_row.addWidget(warn_icon)
            warn_row.addWidget(warn, stretch=1)
            v.addLayout(warn_row)
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
        note.setFont(t.make_font("body"))
        note.setWordWrap(True)
        note.setObjectName("secondary")
        form.addRow(note)
        return page

    # ----------------------------------------------------------------- actions

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.ok_btn.setEnabled(not busy)
        # The Cancel button stays enabled while busy and becomes the way to
        # abort a running Google sign-in.
        self.cancel_btn.setText("Cancel Login" if busy else "Cancel")
        self.type_dropdown.setEnabled(not busy)
        self.stack.setEnabled(not busy)
        self.status_label.setText(message)

    def _oauth_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _request_cancel(self) -> None:
        """Ask the running worker to stop; UI resets when it confirms."""
        if isinstance(self._worker, _GmailAuthWorker):
            self._worker.cancel()
            self.status_label.setText("Cancelling sign-in...")
        else:
            # IMAP verification has a 20 s socket timeout; just let it finish.
            self.status_label.setText("Finishing connection attempt...")

    def reject(self) -> None:
        """Cancel button / Esc: abort a running sign-in instead of closing."""
        if self._oauth_running():
            self._request_cancel()
            return
        super().reject()

    def closeEvent(self, event) -> None:
        """X button: cancel any running sign-in, then close - never the app."""
        if self._oauth_running():
            self._close_after_cancel = True
            self._request_cancel()
            event.ignore()
            return
        event.accept()

    def _on_add(self) -> None:
        if self.type_dropdown.value() == 0:
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
        if isinstance(self._worker, _GmailAuthWorker):
            self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _on_success(self, account: dict) -> None:
        self.added_account = account
        self.accept()

    def _on_failure(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.warning(self, "Could not add account", message)
        if self._close_after_cancel:
            super().reject()

    def _on_cancelled(self) -> None:
        self._set_busy(False, "Sign-in cancelled.")
        if self._close_after_cancel:
            super().reject()

    def shutdown(self) -> None:
        """Cancel any running worker and wait for it (used on app exit)."""
        if self._worker is not None and self._worker.isRunning():
            if isinstance(self._worker, _GmailAuthWorker):
                self._worker.cancel()
            self._worker.wait(5000)

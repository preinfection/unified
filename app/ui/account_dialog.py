"""Add an account.

The first thing a new user does, and previously the roughest surface in
the app: a form with a combo box, a `QFormLayout`, a `QDialogButtonBox`
and modal warnings for every mistake.

Rebuilt as a two-step choice:

1. **Pick a provider.** Two large, obviously-clickable option cards
   rather than a dropdown - with two choices, a dropdown hides one of
   them behind a click and tells you nothing about either.
2. **Do that provider's thing.** Gmail explains what the browser window
   will be and what is stored; IMAP shows the fields, with the server
   details collapsed behind "Advanced" because most providers only need
   an address and a password once the host is filled in.

Behavior worth calling out:

* Cancel means "stop the sign-in", not "close the window", while an
  OAuth flow is running - and closing the window cancels the flow first
  rather than leaving a browser tab waiting for a dead listener.
* Failures land inline, in the dialog that caused them, with the
  provider's own wording kept as detail underneath a sentence that says
  what to actually do about it.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.auth import gmail_oauth
from app.services.account_manager import AccountError, AccountManager
from app.ui import theme as t
from app.ui.components.buttons import AccentButton, Button
from app.ui.components.dialog import AppDialog, divider
from app.ui.svg_icon import themed_pixmap

log = logging.getLogger(__name__)

PROVIDER_GMAIL = 0
PROVIDER_IMAP = 1


class _ProviderCard(QWidget):
    """A large, self-explaining choice. Cards earn their keep here: this
    genuinely is a set of alternatives to compare, which is the one place
    a card is the right container rather than decoration."""

    chosen = Signal(int)

    def __init__(self, provider: int, icon: str, title: str, detail: str, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._icon_name = icon
        self.setProperty("role", "card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(f"{title}. {detail}")

        row = QHBoxLayout(self)
        row.setContentsMargins(t.SPACE_XL, t.SPACE_LG, t.SPACE_XL, t.SPACE_LG)
        row.setSpacing(t.SPACE_LG)

        self._icon = QLabel()
        self._icon.setPixmap(themed_pixmap(icon, t.ICON_LG, "default"))
        row.addWidget(self._icon, alignment=Qt.AlignmentFlag.AlignTop)

        column = QVBoxLayout()
        column.setSpacing(2)
        heading = QLabel(title)
        heading.setFont(t.make_font("body_strong"))
        column.addWidget(heading)
        note = QLabel(detail)
        note.setProperty("tone", "secondary")
        note.setFont(t.make_font("body_sm"))
        note.setWordWrap(True)
        column.addWidget(note)
        row.addLayout(column, stretch=1)

    def set_selected(self, selected: bool) -> None:
        t.set_variant(self, "state", "selected" if selected else None)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.chosen.emit(self._provider)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.chosen.emit(self._provider)
            event.accept()
            return
        super().keyPressEvent(event)


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
    """Verifies the IMAP login and stores the account off the UI thread."""

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


class AccountDialog(AppDialog):
    """Returns the newly added account via self.added_account when accepted."""

    def __init__(self, manager: AccountManager, parent=None):
        super().__init__(
            "Add an account",
            "Connect a Gmail account, or any mailbox that speaks IMAP.",
            parent=parent, width=540,
        )
        self.manager = manager
        self.added_account: dict | None = None
        self._worker: QThread | None = None
        self._close_after_cancel = False
        self._provider = PROVIDER_GMAIL
        self.setModal(False)  # a running sign-in must not block the app

        self._cards = {}
        for provider, icon, title, detail in (
            (PROVIDER_GMAIL, "mail", "Gmail",
             "Sign in with Google. No password is stored - only an OAuth "
             "token, kept in the Windows Credential Manager."),
            (PROVIDER_IMAP, "folder", "Other mailbox (IMAP)",
             "Any provider with IMAP and SMTP. The password is stored in "
             "the Windows Credential Manager, never in a file."),
        ):
            card = _ProviderCard(provider, icon, title, detail)
            card.chosen.connect(self._select_provider)
            self._cards[provider] = card
            self.add_body(card)

        self.add_body(divider())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_gmail_page())
        self.stack.addWidget(self._build_imap_page())
        self.add_body(self.stack, stretch=1)

        self.cancel_btn = Button("Cancel", variant="secondary")
        self.cancel_btn.clicked.connect(self.reject)
        self.add_action(self.cancel_btn)
        self.ok_btn = AccentButton("Add account", size="md", icon="check")
        self.ok_btn.clicked.connect(self._on_add)
        self.add_action(self.ok_btn, primary=True)

        self._select_provider(PROVIDER_GMAIL)

    # ------------------------------------------------------------- pages

    def _build_gmail_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(t.SPACE_MD)

        text = QLabel(
            "Continuing opens your browser to sign in with Google. Unified "
            "asks only for permission to read and send your mail."
        )
        text.setFont(t.make_font("body_sm"))
        text.setProperty("tone", "secondary")
        text.setWordWrap(True)
        column.addWidget(text)

        self._gmail_warning = QWidget()
        self._gmail_warning.setProperty("role", "banner")
        self._gmail_warning.setProperty("tone", "warning")
        warn_row = QHBoxLayout(self._gmail_warning)
        warn_row.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        warn_row.setSpacing(t.SPACE_MD)
        icon = QLabel()
        icon.setPixmap(themed_pixmap("info", t.ICON_SM, "warning"))
        warn_row.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        warn_text = QLabel(
            "Google sign-in is not set up yet. Open Settings > Mail > Google "
            "sign-in and choose your credentials.json first (Google Cloud "
            "Console > APIs & Services > Credentials > OAuth client ID, type "
            "\"Desktop app\", with the Gmail API enabled)."
        )
        warn_text.setFont(t.make_font("body_sm"))
        warn_text.setWordWrap(True)
        warn_row.addWidget(warn_text, stretch=1)
        self._gmail_warning.setVisible(not gmail_oauth.client_secrets_available())
        column.addWidget(self._gmail_warning)
        column.addStretch(1)
        return page

    def _build_imap_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(t.SPACE_MD)

        self.imap_email = self._field("you@example.com")
        column.addWidget(self._labeled("Email address", self.imap_email))

        self.imap_password = self._field("Password or app password")
        self.imap_password.setEchoMode(QLineEdit.EchoMode.Password)
        column.addWidget(self._labeled("Password", self.imap_password))

        self.imap_host = self._field("imap.example.com")
        self.imap_host.textChanged.connect(self._suggest_smtp)
        column.addWidget(self._labeled("IMAP server", self.imap_host))

        self._advanced = QWidget()
        adv = QVBoxLayout(self._advanced)
        adv.setContentsMargins(0, 0, 0, 0)
        adv.setSpacing(t.SPACE_MD)

        self.imap_port = QSpinBox()
        self.imap_port.setRange(1, 65535)
        self.imap_port.setValue(993)
        self.imap_port.setFixedWidth(110)
        adv.addWidget(self._labeled("IMAP port", self.imap_port))

        self.smtp_host = self._field("smtp.example.com")
        adv.addWidget(self._labeled("SMTP server", self.smtp_host))

        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(587)
        self.smtp_port.setFixedWidth(110)
        adv.addWidget(self._labeled("SMTP port", self.smtp_port))
        self._advanced.setVisible(False)
        column.addWidget(self._advanced)

        self._advanced_btn = Button("Server settings", variant="link", size="sm")
        self._advanced_btn.clicked.connect(self._toggle_advanced)
        advanced_row = QHBoxLayout()
        advanced_row.addWidget(self._advanced_btn)
        advanced_row.addStretch(1)
        column.addLayout(advanced_row)

        note = QLabel(
            "For Gmail over IMAP, use an app password rather than your "
            "account password."
        )
        note.setProperty("tone", "tertiary")
        note.setFont(t.make_font("caption"))
        note.setWordWrap(True)
        column.addWidget(note)
        column.addStretch(1)
        return page

    @staticmethod
    def _field(placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        return field

    @staticmethod
    def _labeled(text: str, control: QWidget) -> QWidget:
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(t.SPACE_LG)
        label = QLabel(text)
        label.setFont(t.make_font("field_label"))
        label.setProperty("tone", "secondary")
        label.setFixedWidth(120)
        row.addWidget(label, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(control, stretch=1)
        return wrapper

    def _toggle_advanced(self) -> None:
        showing = not self._advanced.isVisible()
        self._advanced.setVisible(showing)
        self._advanced_btn.setText("Hide server settings" if showing
                                   else "Server settings")

    def _suggest_smtp(self, text: str) -> None:
        """Fill the SMTP host from the IMAP host, which is right for most
        providers - and still editable for the ones where it isn't."""
        if not self.smtp_host.isModified() and text:
            self.smtp_host.setPlaceholderText(text.replace("imap", "smtp"))

    # ---------------------------------------------------------- provider

    def _select_provider(self, provider: int) -> None:
        if self.is_busy:
            return
        self._provider = provider
        self.stack.setCurrentIndex(provider)
        for value, card in self._cards.items():
            card.set_selected(value == provider)
        self.ok_btn.setText(
            "Continue with Google" if provider == PROVIDER_GMAIL else "Add account"
        )

    # ----------------------------------------------------------- actions

    def set_busy(self, busy: bool, message: str = "") -> None:
        super().set_busy(busy, message)
        self.ok_btn.setEnabled(not busy)
        self.cancel_btn.setText("Cancel sign-in" if busy else "Cancel")
        self.stack.setEnabled(not busy)
        for card in self._cards.values():
            card.setEnabled(not busy)

    def _oauth_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _request_cancel(self) -> None:
        if isinstance(self._worker, _GmailAuthWorker):
            self._worker.cancel()
            self.set_status("Cancelling sign-in...")
        else:
            # IMAP verification has a 20s socket timeout; let it finish.
            self.set_status("Finishing the connection attempt...")

    def reject(self) -> None:
        """Cancel / Esc aborts a running sign-in rather than closing."""
        if self._oauth_running():
            self._request_cancel()
            return
        QDialog.reject(self)

    def closeEvent(self, event) -> None:  # noqa: N802
        """The X button cancels any running sign-in, then closes."""
        if self._oauth_running():
            self._close_after_cancel = True
            self._request_cancel()
            event.ignore()
            return
        event.accept()

    def _on_add(self) -> None:
        if self._provider == PROVIDER_GMAIL:
            if not gmail_oauth.client_secrets_available():
                self.set_status(
                    "Set up Google sign-in in Settings first.", tone="danger"
                )
                self._gmail_warning.setVisible(True)
                return
            self.set_busy(True, "Waiting for Google sign-in in your browser...")
            self._worker = _GmailAuthWorker(self.manager, self)
        else:
            email_addr = self.imap_email.text().strip()
            password = self.imap_password.text()
            host = self.imap_host.text().strip()
            if not email_addr:
                self._invalid(self.imap_email, "Enter the email address.")
                return
            if not password:
                self._invalid(self.imap_password, "Enter the password.")
                return
            if not host:
                self._advanced.setVisible(True)
                self._invalid(self.imap_host, "Enter the IMAP server address.")
                return
            params = dict(
                email_addr=email_addr,
                password=password,
                imap_host=host,
                imap_port=self.imap_port.value(),
                smtp_host=self.smtp_host.text().strip() or host.replace("imap", "smtp"),
                smtp_port=self.smtp_port.value(),
            )
            self.set_busy(True, f"Checking the connection to {host}...")
            self._worker = _ImapVerifyWorker(self.manager, params, self)

        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        if isinstance(self._worker, _GmailAuthWorker):
            self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _invalid(self, field: QLineEdit, message: str) -> None:
        t.set_variant(field, "invalid", "true")
        field.setFocus()
        self.set_status(message, tone="danger")

    def _on_success(self, account: dict) -> None:
        self.added_account = account
        self.accept()

    def _on_failure(self, message: str) -> None:
        self.set_busy(False)
        self.set_status(
            "Could not add this account - nothing was changed.", tone="danger"
        )
        from app.ui.components.dialog import report_error

        report_error(
            self, "Could not add this account",
            "Unified could not connect with those details. Your existing "
            "accounts are unaffected.",
            detail=message,
        )
        if self._close_after_cancel:
            QDialog.reject(self)

    def _on_cancelled(self) -> None:
        self.set_busy(False, "Sign-in cancelled.")
        if self._close_after_cancel:
            QDialog.reject(self)

    def shutdown(self) -> None:
        """Cancel any running worker and wait for it (used on app exit)."""
        if self._worker is not None and self._worker.isRunning():
            if isinstance(self._worker, _GmailAuthWorker):
                self._worker.cancel()
            self._worker.wait(5000)

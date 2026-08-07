"""Settings: sync interval, notifications, Google OAuth client file, accounts."""

from __future__ import annotations

import logging
import shutil

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app import config
from app.services.account_manager import AccountManager

log = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Emits accepted() after saving; caller refreshes accounts/timer."""

    def __init__(self, settings: config.Settings, manager: AccountManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.manager = manager
        self.accounts_changed = False

        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- General ---
        general = QGroupBox("General")
        form = QFormLayout(general)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 120)
        self.interval_spin.setSuffix(" min")
        self.interval_spin.setValue(int(settings.get("sync_interval_minutes")))
        self.notify_check = QCheckBox("Show desktop notifications for new mail")
        self.notify_check.setChecked(bool(settings.get("notifications_enabled")))
        self.shown_spin = QSpinBox()
        self.shown_spin.setRange(100, 10000)
        self.shown_spin.setSingleStep(100)
        self.shown_spin.setValue(int(settings.get("messages_shown")))
        form.addRow("Sync every:", self.interval_spin)
        form.addRow("Messages shown per view:", self.shown_spin)
        form.addRow(self.notify_check)
        layout.addWidget(general)

        # --- Google OAuth client ---
        google = QGroupBox("Google OAuth client (for Gmail accounts)")
        gv = QVBoxLayout(google)
        self.google_label = QLabel()
        self.google_label.setWordWrap(True)
        self.google_label.setObjectName("secondary")
        self._update_google_label()
        pick = QPushButton("Select credentials.json...")
        pick.clicked.connect(self._pick_google_file)
        gv.addWidget(self.google_label)
        gv.addWidget(pick)
        layout.addWidget(google)

        # --- Accounts ---
        accounts_box = QGroupBox("Accounts")
        av = QVBoxLayout(accounts_box)
        self.account_list = QListWidget()
        self._reload_accounts()
        remove_row = QHBoxLayout()
        remove_btn = QPushButton("Remove selected account")
        remove_btn.clicked.connect(self._remove_selected)
        remove_row.addWidget(remove_btn)
        remove_row.addStretch(1)
        av.addWidget(self.account_list)
        av.addLayout(remove_row)
        layout.addWidget(accounts_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_google_label(self) -> None:
        if config.google_client_secrets_path().exists():
            self.google_label.setText(
                "OAuth client configured. Gmail accounts can be added."
            )
        else:
            self.google_label.setText(
                "Not configured. Download an OAuth client (type 'Desktop app') "
                "from Google Cloud Console with the Gmail API enabled, then "
                "select the credentials.json file here."
            )

    def _pick_google_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Google OAuth client file", "", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            shutil.copyfile(path, config.google_client_secrets_path())
        except OSError as e:
            QMessageBox.critical(self, "Copy failed", str(e))
            return
        self._update_google_label()

    def _reload_accounts(self) -> None:
        self.account_list.clear()
        for account in self.manager.db.get_accounts():
            item = QListWidgetItem(
                f"{account['email']}  ({account['provider'].upper()})"
            )
            item.setData(0x0100, account["id"])  # Qt.UserRole
            self.account_list.addItem(item)

    def _remove_selected(self) -> None:
        item = self.account_list.currentItem()
        if not item:
            return
        account_id = item.data(0x0100)
        reply = QMessageBox.question(
            self,
            "Remove account",
            f"Remove {item.text()} and its cached emails? "
            "The account itself is not affected.",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.remove_account(account_id)
            self.accounts_changed = True
            self._reload_accounts()

    def _save(self) -> None:
        self.settings.set("sync_interval_minutes", self.interval_spin.value())
        self.settings.set("notifications_enabled", self.notify_check.isChecked())
        self.settings.set("messages_shown", self.shown_spin.value())
        self.accept()

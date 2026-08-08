"""Settings: sync interval, notifications, Google OAuth client file,
accounts - presented as grouped, dividered rows in elevated panels rather
than a stack of QGroupBox frames, matching the rest of the app's cards.
"""

from __future__ import annotations

import logging
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__, config
from app.services.account_manager import AccountManager
from app.ui import theme as t
from app.ui.components.toggle import Toggle
from app.ui.svg_icon import simple_icon

log = logging.getLogger(__name__)


def _divider() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {t.BORDER}; border: none;")
    return line


def _panel(*rows: QWidget) -> QWidget:
    panel = QWidget()
    panel.setObjectName("settingsPanel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    for i, row in enumerate(rows):
        if i > 0:
            layout.addWidget(_divider())
        layout.addWidget(row)
    return panel


def _row(label_text: str, control: QWidget) -> QWidget:
    row = QWidget()
    row.setObjectName("settingsRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(t.SPACE_MD, t.SPACE_SM + 3, t.SPACE_MD, t.SPACE_SM + 3)
    layout.setSpacing(t.SPACE_MD)
    label = QLabel(label_text)
    label.setFont(t.make_font("field_value"))
    layout.addWidget(label, stretch=1)
    layout.addWidget(control, alignment=Qt.AlignmentFlag.AlignVCenter)
    return row


def _group_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("sectionLabel")
    label.setFont(t.make_font("section_label"))
    return label


class SettingsDialog(QDialog):
    """Emits accepted() after saving; caller refreshes accounts/timer."""

    def __init__(self, settings: config.Settings, manager: AccountManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.manager = manager
        self.accounts_changed = False

        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self.setObjectName("settingsDialog")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        outer.setSpacing(t.SPACE_LG)

        # -- header
        header = QHBoxLayout()
        title = QLabel("Settings")
        title.setFont(t.make_font("dialog_heading"))
        header.addWidget(title)
        header.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(t.make_font("button"))
        cancel_btn.clicked.connect(self.reject)
        header.addWidget(cancel_btn)
        save_btn = QPushButton(" Save")
        save_btn.setObjectName("composeButton")
        save_btn.setFont(t.make_font("button"))
        save_btn.setIcon(simple_icon("check", 13, t.TEXT_ON_ACCENT))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        header.addWidget(save_btn)
        outer.addLayout(header)

        # --- General ---
        outer.addWidget(_group_label("General"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setObjectName("settingsControl")
        self.interval_spin.setRange(1, 120)
        self.interval_spin.setSuffix(" min")
        self.interval_spin.setValue(int(settings.get("sync_interval_minutes")))
        self.shown_spin = QSpinBox()
        self.shown_spin.setObjectName("settingsControl")
        self.shown_spin.setRange(100, 10000)
        self.shown_spin.setSingleStep(100)
        self.shown_spin.setValue(int(settings.get("messages_shown")))
        self.notify_toggle = Toggle()
        self.notify_toggle.setChecked(bool(settings.get("notifications_enabled")))
        outer.addWidget(_panel(
            _row("Sync every", self.interval_spin),
            _row("Messages shown per view", self.shown_spin),
            _row("Desktop notifications for new mail", self.notify_toggle),
        ))

        # --- Google OAuth client ---
        outer.addWidget(_group_label("Google account"))
        google_panel = QWidget()
        google_panel.setObjectName("settingsPanel")
        gv = QVBoxLayout(google_panel)
        gv.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        gv.setSpacing(t.SPACE_SM)
        self.google_label = QLabel()
        self.google_label.setFont(t.make_font("body"))
        self.google_label.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
        self.google_label.setWordWrap(True)
        self._update_google_label()
        pick = QPushButton("  Select credentials.json...")
        pick.setFont(t.make_font("button"))
        pick.clicked.connect(self._pick_google_file)
        gv.addWidget(self.google_label)
        gv.addWidget(pick)
        outer.addWidget(google_panel)

        # --- Accounts ---
        outer.addWidget(_group_label("Connected accounts"))
        accounts_panel = QWidget()
        accounts_panel.setObjectName("settingsPanel")
        av = QVBoxLayout(accounts_panel)
        av.setContentsMargins(t.SPACE_SM, t.SPACE_SM, t.SPACE_SM, t.SPACE_SM)
        av.setSpacing(t.SPACE_SM)
        self.account_list = QListWidget()
        self.account_list.setFrameShape(QListWidget.Shape.NoFrame)
        self.account_list.setMaximumHeight(140)
        self._reload_accounts()
        remove_row = QHBoxLayout()
        remove_btn = QPushButton("  Remove selected account")
        remove_btn.setFont(t.make_font("button"))
        remove_btn.setIcon(simple_icon("trash", 13, t.ERROR))
        remove_btn.clicked.connect(self._remove_selected)
        remove_row.addWidget(remove_btn)
        remove_row.addStretch(1)
        av.addWidget(self.account_list)
        av.addLayout(remove_row)
        outer.addWidget(accounts_panel)

        outer.addStretch(1)
        version_label = QLabel(f"{APP_NAME} v{__version__}")
        version_label.setObjectName("tertiary")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(version_label)

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
        self.settings.set("notifications_enabled", self.notify_toggle.isChecked())
        self.settings.set("messages_shown", self.shown_spin.value())
        self.accept()

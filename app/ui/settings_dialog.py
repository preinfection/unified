"""Settings: sync interval, notifications, Google OAuth client file,
accounts - presented as a rail-navigated set of pages (General / Google
account / Connected accounts) rather than one long scrolling column.
Translated from the reference's "rail" layout: a narrow icon+label strip
on the left drives a QStackedWidget on the right, the same structural
pattern the reference uses to keep a settings surface from turning into
an endless scroll once it has more than a couple of groups.
"""

from __future__ import annotations

import logging
import shutil

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
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
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__, config
from app.services.account_manager import AccountManager
from app.ui import theme as t
from app.ui.components.button import AccentButton
from app.ui.components.section_header import DialogHeading, SectionHeader
from app.ui.components.toggle import Toggle
from app.ui.svg_icon import icon_set, simple_icon

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


class _RailItem(QToolButton):
    """One entry in the settings rail: icon above a short label, checked
    when its page is active - the reference's rail-tab anatomy."""

    def __init__(self, icon_name: str, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsRailItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIcon(icon_set(
            icon_name, 20, normal=t.ICON_SECONDARY, active=t.ICON_ACTIVE,
            selected=t.ICON_SELECTED,
        ))
        self.setIconSize(QSize(20, 20))
        self.setText(label)
        self.setFont(t.make_font("caption"))
        self.setFixedWidth(86)


def _page(*widgets: QWidget) -> QWidget:
    page = QWidget()
    col = QVBoxLayout(page)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(t.SPACE_MD)
    for w in widgets:
        col.addWidget(w)
    col.addStretch(1)
    return page


class SettingsDialog(QDialog):
    """Emits accepted() after saving; caller refreshes accounts/timer."""

    def __init__(self, settings: config.Settings, manager: AccountManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.manager = manager
        self.accounts_changed = False

        self.setWindowTitle("Settings")
        self.setMinimumSize(620, 460)
        self.setObjectName("settingsDialog")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        outer.setSpacing(t.SPACE_LG)

        # -- header (stays put across every page)
        header = QHBoxLayout()
        header.addWidget(DialogHeading("Settings"))
        header.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(t.make_font("button"))
        cancel_btn.clicked.connect(self.reject)
        header.addWidget(cancel_btn)
        save_btn = AccentButton(" Save")
        save_btn.setIcon(simple_icon("check", 13, t.TEXT_ON_ACCENT))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        header.addWidget(save_btn)
        outer.addLayout(header)

        # -- rail + pages
        body = QHBoxLayout()
        body.setSpacing(t.SPACE_LG)

        rail_col = QVBoxLayout()
        rail_col.setSpacing(t.SPACE_XS)
        self._rail_group = QButtonGroup(self)
        self._rail_group.setExclusive(True)
        rail_specs = [
            ("settings", "General"),
            ("lock", "Google"),
            ("inbox", "Accounts"),
        ]
        rail_buttons = []
        for icon_name, label in rail_specs:
            btn = _RailItem(icon_name, label)
            self._rail_group.addButton(btn)
            rail_col.addWidget(btn)
            rail_buttons.append(btn)
        rail_col.addStretch(1)
        body.addLayout(rail_col)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_general_page())
        self.stack.addWidget(self._build_google_page())
        self.stack.addWidget(self._build_accounts_page())
        body.addWidget(self.stack, stretch=1)
        outer.addLayout(body, stretch=1)

        for i, btn in enumerate(rail_buttons):
            btn.clicked.connect(lambda _=False, idx=i: self.stack.setCurrentIndex(idx))
        rail_buttons[0].setChecked(True)

        version_label = QLabel(f"{APP_NAME} v{__version__}")
        version_label.setObjectName("tertiary")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(version_label)

    # ------------------------------------------------------------------ pages

    def _build_general_page(self) -> QWidget:
        self.interval_spin = QSpinBox()
        self.interval_spin.setObjectName("settingsControl")
        self.interval_spin.setRange(1, 120)
        self.interval_spin.setSuffix(" min")
        self.interval_spin.setValue(int(self.settings.get("sync_interval_minutes")))
        self.shown_spin = QSpinBox()
        self.shown_spin.setObjectName("settingsControl")
        self.shown_spin.setRange(100, 10000)
        self.shown_spin.setSingleStep(100)
        self.shown_spin.setValue(int(self.settings.get("messages_shown")))
        self.notify_toggle = Toggle()
        self.notify_toggle.setChecked(bool(self.settings.get("notifications_enabled")))
        return _page(
            SectionHeader("General"),
            _panel(
                _row("Sync every", self.interval_spin),
                _row("Messages shown per view", self.shown_spin),
                _row("Desktop notifications for new mail", self.notify_toggle),
            ),
        )

    def _build_google_page(self) -> QWidget:
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
        return _page(SectionHeader("Google account"), google_panel)

    def _build_accounts_page(self) -> QWidget:
        accounts_panel = QWidget()
        accounts_panel.setObjectName("settingsPanel")
        av = QVBoxLayout(accounts_panel)
        av.setContentsMargins(t.SPACE_SM, t.SPACE_SM, t.SPACE_SM, t.SPACE_SM)
        av.setSpacing(t.SPACE_SM)
        self.account_list = QListWidget()
        self.account_list.setFrameShape(QListWidget.Shape.NoFrame)
        self._reload_accounts()
        remove_row = QHBoxLayout()
        remove_btn = QPushButton("  Remove selected account")
        remove_btn.setFont(t.make_font("button"))
        remove_btn.setIcon(simple_icon("trash", 13, t.ERROR))
        remove_btn.clicked.connect(self._remove_selected)
        remove_row.addWidget(remove_btn)
        remove_row.addStretch(1)
        av.addWidget(self.account_list, stretch=1)
        av.addLayout(remove_row)
        return _page(SectionHeader("Connected accounts"), accounts_panel)

    # ------------------------------------------------------------------ misc

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

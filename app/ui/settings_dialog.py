"""Settings.

Rebuilt around what a person is actually looking for rather than around
what the code happens to store. Four pages, each one answerable in a
sentence:

    Appearance   how the app looks       theme, list density
    Mail         how mail behaves        sync interval, page size, notifications
    Accounts     which mail              connected accounts, add, remove
    About        what this is            version, where data lives, privacy

Structural decisions:

* A left rail of text destinations, not icons-above-tiny-labels. Four
  items with real names are faster to read than four pictograms, and the
  rail matches the sidebar's navigation language so the app has one idea
  of what "a list of destinations" looks like.
* Settings are grouped into panels with hairline separators, not one card
  per setting. A card per row turns a settings page into a spreadsheet of
  boxes and destroys any sense of grouping.
* Every row is label + description + control. The description is where a
  setting explains its consequence, which is the thing users need and the
  thing a bare label never tells them.
* Appearance applies live as it is changed. A theme picker you have to
  press Save to evaluate is a theme picker you cannot evaluate.
"""

from __future__ import annotations

import logging
import shutil

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__, config
from app.services.account_manager import AccountManager
from app.ui import theme as t
from app.ui.components.buttons import AccentButton, Button
from app.ui.components.dialog import AppDialog, confirm, divider, notify, report_error
from app.ui.components.dropdown import Dropdown
from app.ui.components.section_header import SectionHeader
from app.ui.components.toggle import Toggle
from app.ui.svg_icon import themed_pixmap

log = logging.getLogger(__name__)


def _avatar_pixmap(email: str) -> QPixmap:
    from app.ui.components.avatar import paint_avatar

    size = t.AVATAR_SM
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    paint_avatar(painter, QRectF(0, 0, size, size), email, "", email)
    painter.end()
    return pixmap


def _panel(*rows: QWidget) -> QWidget:
    panel = QWidget()
    panel.setProperty("role", "panel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    for i, row in enumerate(rows):
        if i:
            layout.addWidget(divider())
        layout.addWidget(row)
    return panel


def _row(label_text: str, control: QWidget, description: str = "") -> QWidget:
    """One setting: what it is, what it does, and the control for it."""
    row = QWidget()
    row.setObjectName("settingsRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(t.SPACE_XL, t.SPACE_LG, t.SPACE_XL, t.SPACE_LG)
    layout.setSpacing(t.SPACE_XL)

    text = QVBoxLayout()
    text.setSpacing(1)
    label = QLabel(label_text)
    label.setFont(t.make_font("field_value"))
    text.addWidget(label)
    if description:
        note = QLabel(description)
        note.setProperty("tone", "tertiary")
        note.setFont(t.make_font("caption"))
        note.setWordWrap(True)
        text.addWidget(note)
    layout.addLayout(text, stretch=1)
    layout.addWidget(control, alignment=Qt.AlignmentFlag.AlignVCenter)
    return row


def _page(*widgets: QWidget) -> QWidget:
    page = QWidget()
    column = QVBoxLayout(page)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(t.SPACE_LG)
    for widget in widgets:
        column.addWidget(widget)
    column.addStretch(1)
    return page


class SettingsDialog(AppDialog):
    """Emits accepted() after saving; the caller refreshes accounts/timers."""

    def __init__(self, settings: config.Settings, manager: AccountManager, parent=None):
        super().__init__(
            "Settings", "Appearance, mail behavior and connected accounts",
            parent=parent, width=720,
        )
        self.settings = settings
        self.manager = manager
        self.accounts_changed = False
        self.setMinimumHeight(520)
        # Appearance changes are applied immediately, so cancelling has to
        # be able to put them back exactly as they were.
        self._original_theme = t.theme_manager.mode
        self._original_density = t.theme_manager.density

        body = QHBoxLayout()
        body.setSpacing(t.SPACE_2XL)

        rail = QVBoxLayout()
        rail.setSpacing(t.SPACE_2XS)
        self._rail_group = QButtonGroup(self)
        self._rail_group.setExclusive(True)
        rail_buttons = []
        for label in ("Appearance", "Mail", "Accounts", "About"):
            button = Button(label, variant="subtle", size="md")
            button.setObjectName("settingsRailItem")
            button.setCheckable(True)
            button.setMinimumWidth(150)
            self._rail_group.addButton(button)
            rail.addWidget(button)
            rail_buttons.append(button)
        rail.addStretch(1)
        body.addLayout(rail)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_appearance_page())
        self.stack.addWidget(self._build_mail_page())
        self.stack.addWidget(self._build_accounts_page())
        self.stack.addWidget(self._build_about_page())
        body.addWidget(self.stack, stretch=1)
        self.body.addLayout(body, stretch=1)

        for index, button in enumerate(rail_buttons):
            button.clicked.connect(lambda _=False, i=index: self.stack.setCurrentIndex(i))
        rail_buttons[0].setChecked(True)

        cancel = Button("Cancel", variant="secondary")
        cancel.clicked.connect(self.reject)
        self.add_action(cancel)
        save = AccentButton("Save", size="md", icon="check")
        save.clicked.connect(self._save)
        self.add_action(save, primary=True)

    # ------------------------------------------------------------- pages

    def _build_appearance_page(self) -> QWidget:
        self.theme_dropdown = Dropdown(
            [("Match Windows", "system"), ("Light", "light"), ("Dark", "dark")],
            current=t.theme_manager.mode,
        )
        self.theme_dropdown.changed.connect(self._on_theme_changed)

        self.density_dropdown = Dropdown(
            [(value.capitalize(), value) for value in t.DENSITY_ORDER],
            current=t.theme_manager.density,
        )
        self.density_dropdown.changed.connect(t.theme_manager.set_density)

        return _page(
            SectionHeader("Appearance"),
            _panel(
                _row(
                    "Theme", self.theme_dropdown,
                    "Match Windows follows your system light/dark setting.",
                ),
                _row(
                    "Message list density", self.density_dropdown,
                    "How much detail each row in the message list shows.",
                ),
            ),
        )

    def _build_mail_page(self) -> QWidget:
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 120)
        self.interval_spin.setSuffix(" min")
        self.interval_spin.setValue(int(self.settings.get("sync_interval_minutes")))
        self.interval_spin.setFixedWidth(110)

        self.shown_spin = QSpinBox()
        self.shown_spin.setRange(50, 10000)
        self.shown_spin.setSingleStep(50)
        self.shown_spin.setValue(int(self.settings.get("messages_shown")))
        self.shown_spin.setFixedWidth(110)

        self.notify_toggle = Toggle()
        self.notify_toggle.setChecked(bool(self.settings.get("notifications_enabled")))

        return _page(
            SectionHeader("Syncing"),
            _panel(
                _row(
                    "Check for new mail every", self.interval_spin,
                    "Unified also syncs when you press Refresh or open the app.",
                ),
                _row(
                    "Messages loaded per view", self.shown_spin,
                    "Older messages stay cached and load as you scroll. "
                    "A smaller number makes the first screen appear sooner.",
                ),
            ),
            SectionHeader("Notifications"),
            _panel(
                _row(
                    "Notify me about new mail", self.notify_toggle,
                    "A desktop notification when a sync finds new messages.",
                ),
            ),
            SectionHeader("Google sign-in"),
            self._build_google_panel(),
        )

    def _build_google_panel(self) -> QWidget:
        panel = QWidget()
        panel.setProperty("role", "panel")
        column = QVBoxLayout(panel)
        column.setContentsMargins(t.SPACE_XL, t.SPACE_LG, t.SPACE_XL, t.SPACE_LG)
        column.setSpacing(t.SPACE_LG)

        status_row = QHBoxLayout()
        status_row.setSpacing(t.SPACE_MD)
        self._google_icon = QLabel()
        status_row.addWidget(self._google_icon, alignment=Qt.AlignmentFlag.AlignTop)
        self.google_label = QLabel()
        self.google_label.setFont(t.make_font("body_sm"))
        self.google_label.setWordWrap(True)
        status_row.addWidget(self.google_label, stretch=1)
        column.addLayout(status_row)

        pick = Button("Choose credentials.json...", variant="secondary", icon="folder")
        pick.clicked.connect(self._pick_google_file)
        button_row = QHBoxLayout()
        button_row.addWidget(pick)
        button_row.addStretch(1)
        column.addLayout(button_row)

        self._update_google_label()
        return panel

    def _build_accounts_page(self) -> QWidget:
        panel = QWidget()
        panel.setProperty("role", "panel")
        column = QVBoxLayout(panel)
        column.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        column.setSpacing(t.SPACE_MD)

        self.account_list = QListWidget()
        self.account_list.setFrameShape(QListWidget.Shape.NoFrame)
        self.account_list.setMinimumHeight(200)
        self.account_list.setIconSize(QSize(t.AVATAR_SM, t.AVATAR_SM))
        self.account_list.setAccessibleName("Connected accounts")
        self._reload_accounts()
        column.addWidget(self.account_list, stretch=1)

        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_MD)
        self.remove_btn = Button(
            "Remove account", variant="danger_quiet", icon="trash",
            tooltip="Disconnect this account and delete its cached mail",
        )
        self.remove_btn.clicked.connect(self._remove_selected)
        self.remove_btn.setEnabled(False)
        actions.addWidget(self.remove_btn)
        actions.addStretch(1)
        column.addLayout(actions)

        self.account_list.itemSelectionChanged.connect(
            lambda: self.remove_btn.setEnabled(
                self.account_list.currentItem() is not None
            )
        )

        note = QLabel(
            "Removing an account deletes only Unified's local copy of its "
            "mail. Nothing is deleted on the mail server."
        )
        note.setProperty("tone", "tertiary")
        note.setFont(t.make_font("caption"))
        note.setWordWrap(True)

        return _page(SectionHeader("Connected accounts"), panel, note)

    def _build_about_page(self) -> QWidget:
        panel = QWidget()
        panel.setProperty("role", "panel")
        column = QVBoxLayout(panel)
        column.setContentsMargins(t.SPACE_XL, t.SPACE_XL, t.SPACE_XL, t.SPACE_XL)
        column.setSpacing(t.SPACE_MD)

        title = QLabel(f"{APP_NAME} {__version__}")
        title.setFont(t.make_font("subheading"))
        column.addWidget(title)

        description = QLabel(
            "A desktop mail client that keeps several accounts in one "
            "mailbox. Mail is cached on this machine and encrypted at rest; "
            "passwords and OAuth tokens are stored in the Windows Credential "
            "Manager, never in a file."
        )
        description.setProperty("tone", "secondary")
        description.setFont(t.make_font("body_sm"))
        description.setWordWrap(True)
        column.addWidget(description)

        location = QLabel(f"Data folder:  {config.app_data_dir()}")
        location.setProperty("tone", "tertiary")
        location.setFont(t.make_font("caption", mono=True))
        location.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        location.setWordWrap(True)
        column.addWidget(location)

        return _page(SectionHeader("About"), panel)

    # -------------------------------------------------------------- misc

    def _on_theme_changed(self, mode: str) -> None:
        t.theme_manager.set_mode(mode)

    def _update_google_label(self) -> None:
        configured = config.google_client_secrets_path().exists()
        self._google_icon.setPixmap(
            themed_pixmap(
                "check_circle" if configured else "info", t.ICON_SM,
                "success" if configured else "default",
            )
        )
        if configured:
            self.google_label.setText(
                "An OAuth client is configured. You can add Gmail accounts."
            )
        else:
            self.google_label.setText(
                "Not configured yet. Gmail sign-in needs an OAuth client file "
                "from the Google Cloud Console: create a project, enable the "
                "Gmail API, then create an OAuth client ID of type "
                "\"Desktop app\" and choose the downloaded credentials.json "
                "here. IMAP accounts do not need this."
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
            report_error(
                self, "Could not save that file",
                "Unified could not copy the credentials file into its data "
                "folder. The previous setting is unchanged.",
                detail=str(e),
            )
            return
        self._update_google_label()
        notify(
            self, "Google sign-in ready",
            "You can now add a Gmail account from the sidebar.",
        )

    def _reload_accounts(self) -> None:
        """One row per account: its own avatar (the same color it has in
        the sidebar and the message list), the address, and the provider -
        so the row is recognisable rather than a line of text."""
        self.account_list.clear()
        accounts = self.manager.db.get_accounts()
        for account in accounts:
            provider = "Gmail" if account["provider"] == "gmail" else "IMAP"
            item = QListWidgetItem(f"{account['email']}      {provider}")
            item.setIcon(QIcon(_avatar_pixmap(account["email"])))
            item.setData(Qt.ItemDataRole.UserRole, account["id"])
            item.setToolTip(account["email"])
            self.account_list.addItem(item)
        if not accounts:
            placeholder = QListWidgetItem("No accounts connected yet")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.account_list.addItem(placeholder)

    def _remove_selected(self) -> None:
        item = self.account_list.currentItem()
        if not item:
            return
        account_id = item.data(Qt.ItemDataRole.UserRole)
        if account_id is None:
            return
        if not confirm(
            self, "Remove this account?",
            f"{item.text().split('    ·    ')[0]} will be disconnected and its "
            "cached messages deleted from this computer.",
            confirm_text="Remove", destructive=True,
            detail="Nothing is deleted on the mail server.",
        ):
            return
        self.manager.remove_account(account_id)
        self.accounts_changed = True
        self._reload_accounts()
        self.remove_btn.setEnabled(False)

    # -------------------------------------------------------------- save

    def _save(self) -> None:
        self.settings.set("sync_interval_minutes", self.interval_spin.value())
        self.settings.set("notifications_enabled", self.notify_toggle.isChecked())
        self.settings.set("messages_shown", self.shown_spin.value())
        self.settings.set("theme_mode", t.theme_manager.mode)
        self.settings.set("list_density", t.theme_manager.density)
        self.accept()

    def reject(self) -> None:
        # Appearance previews live; cancelling must undo them.
        t.theme_manager.set_mode(self._original_theme)
        t.theme_manager.set_density(self._original_density)
        super().reject()

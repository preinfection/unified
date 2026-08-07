"""Main window: sidebar / email list / preview, toolbar, tray, sync wiring."""

from __future__ import annotations

import html
import logging
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTextBrowser,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.database import Database
from app.services.account_manager import AccountManager
from app.services.notifier import Notifier
from app.services.sync_service import RemoteActionWorker, SyncWorker
from app.ui.account_dialog import AccountDialog
from app.ui.compose_dialog import ComposeDialog
from app.ui.icons import make_app_icon
from app.ui.settings_dialog import SettingsDialog

log = logging.getLogger(__name__)

VIEW_ITEMS = [
    ("inbox", "Unified Inbox"),
    ("starred", "Starred"),
    ("sent", "Sent"),
    ("trash", "Trash"),
]


class MainWindow(QMainWindow):
    def __init__(self, db: Database, settings: config.Settings):
        super().__init__()
        self.db = db
        self.settings = settings
        self.manager = AccountManager(db)

        self.current_view = "inbox"          # inbox | starred | sent | trash
        self.current_account_id: int | None = None
        self.current_email_id: int | None = None
        self._sync_worker: SyncWorker | None = None
        self._action_workers: list[RemoteActionWorker] = []
        self._account_dialog: AccountDialog | None = None
        # account_id -> (detail, done, total) for the live progress panel
        self._sync_progress: dict[int, tuple[str, int, int]] = {}
        self._panel_account_id: int | None = None

        self.setWindowTitle("Unified Mailbox")
        self.setWindowIcon(make_app_icon())
        self.resize(1200, 720)

        self._build_toolbar()
        self._build_body()
        self._build_tray()
        self.statusBar().showMessage("Ready")

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.reload_email_list)

        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self.start_sync)
        self._apply_sync_interval()

        self.reload_sidebar()
        self.reload_email_list()
        if self.db.get_accounts():
            QTimer.singleShot(400, self.start_sync)

    # ------------------------------------------------------------------ toolbar

    def _build_toolbar(self) -> None:
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        compose_btn = QPushButton("Compose")
        compose_btn.setDefault(True)
        compose_btn.clicked.connect(self.open_compose)
        toolbar.addWidget(compose_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.start_sync)
        toolbar.addWidget(refresh_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search all accounts...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(320)
        self.search_edit.textChanged.connect(
            lambda: self._search_timer.start()
        )
        toolbar.addWidget(self.search_edit)

    # --------------------------------------------------------------------- body

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # -- Sidebar
        self.sidebar = QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setRootIsDecorated(False)
        self.sidebar.setFixedWidth(220)
        self.sidebar.itemClicked.connect(self._on_sidebar_clicked)
        splitter.addWidget(self.sidebar)

        # -- Email list
        self.email_list = QTreeWidget()
        self.email_list.setRootIsDecorated(False)
        self.email_list.setAlternatingRowColors(True)
        self.email_list.setHeaderLabels(["", "From", "Subject", "Account", "Time"])
        self.email_list.setColumnWidth(0, 36)
        self.email_list.setColumnWidth(1, 150)
        self.email_list.setColumnWidth(2, 240)
        self.email_list.setColumnWidth(3, 150)
        self.email_list.itemSelectionChanged.connect(self._on_email_selected)
        self.email_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.email_list.customContextMenuRequested.connect(self._email_context_menu)

        # The center area is a stack: page 0 = message list, page 1 = the
        # plain sync/loading panel shown while an account's initial import runs.
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.email_list)
        self.center_stack.addWidget(self._build_sync_panel())
        splitter.addWidget(self.center_stack)

        # -- Preview panel
        preview = QWidget()
        pv = QVBoxLayout(preview)
        pv.setContentsMargins(12, 10, 12, 10)
        pv.setSpacing(6)

        self.preview_subject = QLabel("Select an email")
        self.preview_subject.setObjectName("heading")
        self.preview_subject.setWordWrap(True)
        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("secondary")
        self.preview_meta.setWordWrap(True)

        actions_row = QHBoxLayout()
        self.star_btn = QPushButton("Star")
        self.star_btn.clicked.connect(self._toggle_star)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete_current)
        for b in (self.star_btn, self.delete_btn):
            b.setEnabled(False)
            actions_row.addWidget(b)
        actions_row.addStretch(1)

        self.preview_body = QTextBrowser()
        self.preview_body.setOpenExternalLinks(True)

        pv.addWidget(self.preview_subject)
        pv.addWidget(self.preview_meta)
        pv.addLayout(actions_row)
        pv.addWidget(self.preview_body, stretch=1)
        splitter.addWidget(preview)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 4)
        splitter.setSizes([220, 620, 360])

    def _build_sync_panel(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.addStretch(2)

        inner = QVBoxLayout()
        inner.setSpacing(8)
        self.sync_account_label = QLabel("")
        self.sync_account_label.setObjectName("heading")
        self.sync_account_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sync_status_label = QLabel("Syncing mailbox...")
        self.sync_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sync_bar = QProgressBar()
        self.sync_bar.setFixedWidth(320)
        self.sync_bar.setTextVisible(False)
        self.sync_detail_label = QLabel("")
        self.sync_detail_label.setObjectName("secondary")
        self.sync_detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        inner.addWidget(self.sync_account_label)
        inner.addWidget(self.sync_status_label)
        inner.addWidget(self.sync_bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        inner.addWidget(self.sync_detail_label)
        outer.addLayout(inner)
        outer.addStretch(3)
        return panel

    # --------------------------------------------------------------------- tray

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.setToolTip("Unified Mailbox")
        menu = QMenu()
        show_action = QAction("Open", menu)
        show_action.triggered.connect(self._show_from_tray)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.show()
        self.notifier = Notifier(self.tray, self.settings)

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()

    def _quit(self) -> None:
        self.tray.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    # ------------------------------------------------------------------ sidebar

    def reload_sidebar(self) -> None:
        counts = self.db.unread_counts()
        self.sidebar.clear()

        bold = QFont()
        bold.setBold(True)

        for view, label in VIEW_ITEMS:
            text = label
            if view == "inbox" and counts["total"]:
                text = f"{label} ({counts['total']})"
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.ItemDataRole.UserRole, ("view", view))
            if view == "inbox":
                item.setFont(0, bold)
            self.sidebar.addTopLevelItem(item)

        accounts_header = QTreeWidgetItem(["ACCOUNTS"])
        accounts_header.setFlags(Qt.ItemFlag.NoItemFlags)
        self.sidebar.addTopLevelItem(accounts_header)

        for account in self.db.get_accounts():
            unread = counts["per_account"].get(account["id"], 0)
            text = f"  {account['email']}"
            if unread:
                text += f" ({unread})"
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.ItemDataRole.UserRole, ("account", account["id"]))
            item.setToolTip(0, f"{account['email']} - {account['provider'].upper()}")
            self.sidebar.addTopLevelItem(item)

        add_item = QTreeWidgetItem(["  + Add account..."])
        add_item.setData(0, Qt.ItemDataRole.UserRole, ("add", None))
        self.sidebar.addTopLevelItem(add_item)

        settings_item = QTreeWidgetItem(["Settings"])
        settings_item.setData(0, Qt.ItemDataRole.UserRole, ("settings", None))
        self.sidebar.addTopLevelItem(settings_item)

    def _on_sidebar_clicked(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, value = data
        if kind == "view":
            self.current_view = value
            self.current_account_id = None
        elif kind == "account":
            self.current_view = "inbox"
            self.current_account_id = value
        elif kind == "add":
            self.open_add_account()
            return
        elif kind == "settings":
            self.open_settings()
            return
        self.reload_email_list()

    # --------------------------------------------------------------- email list

    def reload_email_list(self) -> None:
        search = self.search_edit.text().strip()
        starred = self.current_view == "starred"
        folder = self.current_view if not starred else "inbox"
        emails = self.db.list_emails(
            folder=folder,
            account_id=self.current_account_id,
            starred_only=starred,
            search=search,
            limit=int(self.settings.get("messages_shown")),
        )

        self.email_list.blockSignals(True)
        self.email_list.clear()
        bold = QFont()
        bold.setBold(True)

        for msg in emails:
            sender = msg["sender_name"] or msg["sender_email"] or "(unknown)"
            subject = msg["subject"] or "(no subject)"
            if msg["has_attachments"]:
                subject = "[a] " + subject
            marker = "●" if not msg["is_read"] else ""
            if msg["is_starred"]:
                marker = ("★" + marker) if marker else "★"
            item = QTreeWidgetItem(
                [marker, sender, subject, msg["account_email"],
                 self._format_time(msg["date_ts"])]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, msg["id"])
            if not msg["is_read"]:
                for col in range(5):
                    item.setFont(col, bold)
            item.setToolTip(2, msg["snippet"])
            self.email_list.addTopLevelItem(item)

        self.email_list.blockSignals(False)
        n = len(emails)
        self.statusBar().showMessage(f"{n} message{'s' if n != 1 else ''}")
        self._refresh_center_page(n)

    def _refresh_center_page(self, email_count: int) -> None:
        """Choose between the message list and the sync/loading panel.

        The panel is shown while looking at an account whose initial import
        has not completed, or on a unified inbox that is empty only because
        the first account is still importing.
        """
        pending = {
            a["id"]: a
            for a in self.db.get_accounts()
            if not a["initial_sync_completed"]
        }
        account = None
        if self.current_account_id in pending:
            account = pending[self.current_account_id]
        elif (
            email_count == 0
            and pending
            and self.current_view == "inbox"
            and self.current_account_id is None
            and not self.search_edit.text().strip()
        ):
            account = next(iter(pending.values()))
        if account is None:
            self._panel_account_id = None
            self.center_stack.setCurrentIndex(0)
            return
        self._panel_account_id = account["id"]
        self._update_sync_panel(account)
        self.center_stack.setCurrentIndex(1)

    def _update_sync_panel(self, account: dict) -> None:
        self.sync_account_label.setText(account["email"])
        progress = self._sync_progress.get(account["id"])
        syncing = self._sync_worker is not None and self._sync_worker.isRunning()
        if progress:
            detail, done, total = progress
            self.sync_status_label.setText("Syncing mailbox...")
            self.sync_detail_label.setText(
                f"{detail}  ({done}/{total})" if total else detail
            )
            if total:
                self.sync_bar.setRange(0, total)
                self.sync_bar.setValue(done)
            else:
                self.sync_bar.setRange(0, 0)  # busy indicator
        elif syncing:
            self.sync_status_label.setText("Syncing mailbox...")
            self.sync_detail_label.setText("Fetching emails...")
            self.sync_bar.setRange(0, 0)
        else:
            self.sync_status_label.setText("Loading mailbox...")
            self.sync_detail_label.setText(
                "Fetching emails - preparing search index..."
            )
            self.sync_bar.setRange(0, 0)

    @staticmethod
    def _format_time(ts: int) -> str:
        if not ts:
            return ""
        dt = datetime.fromtimestamp(ts)
        now = datetime.now()
        if dt.date() == now.date():
            return dt.strftime("%H:%M")
        if dt.year == now.year:
            return dt.strftime("%d %b")
        return dt.strftime("%d %b %Y")

    # ------------------------------------------------------------------ preview

    def _on_email_selected(self) -> None:
        items = self.email_list.selectedItems()
        if not items:
            return
        email_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        msg = self.db.get_email(email_id)
        if not msg:
            return
        self.current_email_id = email_id

        self.preview_subject.setText(msg["subject"] or "(no subject)")
        sender = msg["sender_name"] or msg["sender_email"]
        meta = (
            f"From: {sender} &lt;{html.escape(msg['sender_email'])}&gt;<br>"
            f"To: {html.escape(msg['recipients'] or '')}<br>"
            f"Account: {html.escape(msg['account_email'])}"
            f" &nbsp;|&nbsp; {self._format_time(msg['date_ts'])}"
        )
        if msg["has_attachments"]:
            meta += " &nbsp;|&nbsp; has attachments"
        self.preview_meta.setText(meta)

        if msg["body_html"]:
            self.preview_body.setHtml(msg["body_html"])
        else:
            self.preview_body.setPlainText(msg["body_text"] or msg["snippet"] or "")

        self.star_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.star_btn.setText("Unstar" if msg["is_starred"] else "Star")

        if not msg["is_read"]:
            self.db.set_read(email_id, True)
            self._remote_action(msg, "read", True)
            self.reload_email_list()
            self.reload_sidebar()

    # ------------------------------------------------------------------ actions

    def _remote_action(self, msg: dict, action: str, value: bool = True) -> None:
        account = self.db.get_account(msg["account_id"])
        if not account:
            return
        worker = RemoteActionWorker(account, action, msg["uid"], msg["folder"], value)
        worker.failed.connect(
            lambda err: self.statusBar().showMessage(f"Server update failed: {err}")
        )
        worker.finished.connect(lambda: self._action_workers.remove(worker))
        self._action_workers.append(worker)
        worker.start()

    def _toggle_star(self) -> None:
        if self.current_email_id is None:
            return
        msg = self.db.get_email(self.current_email_id)
        if not msg:
            return
        new_state = not msg["is_starred"]
        self.db.set_starred(self.current_email_id, new_state)
        self._remote_action(msg, "star", new_state)
        self.star_btn.setText("Unstar" if new_state else "Star")
        self.reload_email_list()

    def _delete_current(self) -> None:
        if self.current_email_id is None:
            return
        msg = self.db.get_email(self.current_email_id)
        if not msg:
            return
        if msg["folder"] == "trash":
            QMessageBox.information(
                self, "Already in Trash", "This message is already in the trash."
            )
            return
        self.db.move_to_trash(self.current_email_id)
        self._remote_action(msg, "trash")
        self.current_email_id = None
        self.preview_subject.setText("Select an email")
        self.preview_meta.setText("")
        self.preview_body.clear()
        self.star_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.reload_email_list()
        self.reload_sidebar()

    def _email_context_menu(self, pos) -> None:
        item = self.email_list.itemAt(pos)
        if not item:
            return
        email_id = item.data(0, Qt.ItemDataRole.UserRole)
        msg = self.db.get_email(email_id)
        if not msg:
            return
        menu = QMenu(self)
        mark = menu.addAction(
            "Mark as unread" if msg["is_read"] else "Mark as read"
        )
        star = menu.addAction("Unstar" if msg["is_starred"] else "Star")
        delete = menu.addAction("Delete")
        chosen = menu.exec(self.email_list.viewport().mapToGlobal(pos))
        if chosen == mark:
            new_read = not msg["is_read"]
            self.db.set_read(email_id, new_read)
            self._remote_action(msg, "read", new_read)
        elif chosen == star:
            new_star = not msg["is_starred"]
            self.db.set_starred(email_id, new_star)
            self._remote_action(msg, "star", new_star)
        elif chosen == delete:
            self.current_email_id = email_id
            self._delete_current()
            return
        self.reload_email_list()
        self.reload_sidebar()

    # --------------------------------------------------------------------- sync

    def _apply_sync_interval(self) -> None:
        minutes = int(self.settings.get("sync_interval_minutes"))
        self._sync_timer.start(minutes * 60 * 1000)

    def start_sync(self) -> None:
        if self._sync_worker is not None and self._sync_worker.isRunning():
            self.statusBar().showMessage("Sync already in progress")
            return
        if not self.db.get_accounts():
            self.statusBar().showMessage("Add an account to start syncing")
            return
        self._sync_worker = SyncWorker(self.db.path)
        self._sync_worker.progress.connect(self.statusBar().showMessage)
        self._sync_worker.account_progress.connect(self._on_account_progress)
        self._sync_worker.account_finished.connect(self._on_account_finished)
        self._sync_worker.account_failed.connect(
            lambda err: self.statusBar().showMessage(f"Sync error - {err}")
        )
        self._sync_worker.finished_sync.connect(self._on_sync_finished)
        self._sync_worker.start()

    def _on_account_progress(
        self, account_id: int, detail: str, done: int, total: int
    ) -> None:
        self._sync_progress[account_id] = (detail, done, total)
        if self._panel_account_id == account_id:
            account = self.db.get_account(account_id)
            if account:
                self._update_sync_panel(account)

    def _on_account_finished(
        self, account_id: int, imported: int, was_initial: bool
    ) -> None:
        self._sync_progress.pop(account_id, None)
        # Reload so a finished initial import replaces its loading panel
        # with the populated list immediately. The reload writes its own
        # status text, so the completion message goes up afterwards.
        self.reload_sidebar()
        self.reload_email_list()
        if was_initial:
            plural = "s" if imported != 1 else ""
            self.statusBar().showMessage(
                f"Mailbox ready - imported {imported} existing email{plural}"
            )

    def _on_sync_finished(self, new_count: int) -> None:
        self._sync_progress.clear()
        self.reload_email_list()
        self.reload_sidebar()
        if new_count:
            plural = "s" if new_count != 1 else ""
            self.statusBar().showMessage(
                f"Sync complete - {new_count} new message{plural}"
            )
        self.notifier.notify_new_mail(new_count)

    # ------------------------------------------------------------------ dialogs

    def open_compose(self) -> None:
        accounts = self.db.get_accounts()
        if not accounts:
            QMessageBox.information(
                self, "No accounts", "Add an email account first."
            )
            return
        dialog = ComposeDialog(accounts, self)
        dialog.sent.connect(lambda: self.statusBar().showMessage("Message sent"))
        dialog.exec()

    def open_add_account(self) -> None:
        # Non-modal so a running Google sign-in never blocks the main window.
        if self._account_dialog is not None:
            self._account_dialog.raise_()
            self._account_dialog.activateWindow()
            return
        dialog = AccountDialog(self.manager, self)
        dialog.finished.connect(lambda _: self._on_account_dialog_done(dialog))
        self._account_dialog = dialog
        dialog.show()

    def _on_account_dialog_done(self, dialog: AccountDialog) -> None:
        self._account_dialog = None
        account = dialog.added_account
        dialog.deleteLater()
        if account:
            # Jump straight to the new account: its initial import shows the
            # progress panel instead of an empty inbox.
            self.current_view = "inbox"
            self.current_account_id = account["id"]
            self.reload_sidebar()
            self.reload_email_list()
            self.start_sync()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.manager, self)
        if dialog.exec():
            self._apply_sync_interval()
            if dialog.accounts_changed:
                self.reload_sidebar()
                self.reload_email_list()

    # ------------------------------------------------------------------- close

    def closeEvent(self, event) -> None:
        # Stop background timers; let running workers finish quickly.
        self._sync_timer.stop()
        if self._account_dialog is not None:
            self._account_dialog.shutdown()
            self._account_dialog.close()
        if self._sync_worker is not None and self._sync_worker.isRunning():
            self._sync_worker.wait(3000)
        for worker in list(self._action_workers):
            worker.wait(1000)
        self.tray.hide()
        event.accept()

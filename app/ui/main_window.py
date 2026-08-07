"""Main window: sidebar / email list / preview, toolbar, console, sync wiring.

Threading rules kept here:
- All network work (sync, body fetch, remote flag updates) runs on QThreads.
- UI reloads triggered by sync signals are coalesced through a single-shot
  timer so heavy sync activity cannot cause reload storms or lag spikes.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QFont
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
from app.services.sync_service import (
    PH_BODIES,
    PH_CONNECT,
    PH_INDEX,
    PH_LIST,
    PH_META,
    PH_VERIFY,
    ST_DONE,
    ST_ERROR,
    ST_PARTIAL,
    ST_SYNCING,
    ST_WAITING,
    BodyFetchWorker,
    RemoteActionWorker,
    SyncManager,
)

# Friendly first-launch wording for each sync phase (panel display)
PHASE_TEXT = {
    PH_CONNECT: "Connecting account...",
    PH_LIST: "Downloading message list...",
    PH_META: "Downloading message list...",
    PH_BODIES: "Downloading message content...",
    PH_INDEX: "Preparing mailbox...",
    PH_VERIFY: "Preparing mailbox...",
}
from app.ui.account_dialog import AccountDialog
from app.ui.compose_dialog import ComposeDialog
from app.ui.console import ConsoleWidget
from app.ui.html_view import HtmlMailView
from app.ui.icons import make_app_icon
from app.ui.native_theme import apply_white_titlebar
from app.ui.settings_dialog import SettingsDialog

log = logging.getLogger(__name__)

VIEW_ITEMS = [
    ("inbox", "Unified Inbox"),
    ("starred", "Starred"),
    ("sent", "Sent"),
    ("trash", "Trash"),
]

STATUS_GRAY = QBrush(QColor("#666666"))


class MainWindow(QMainWindow):
    def __init__(self, db: Database, settings: config.Settings):
        super().__init__()
        self.db = db
        self.settings = settings
        self.manager = AccountManager(db)
        self.sync = SyncManager(db.path, self)

        self.current_view = "inbox"          # inbox | starred | sent | trash
        self.current_account_id: int | None = None
        self.current_email_id: int | None = None
        self._account_dialog: AccountDialog | None = None
        self._action_workers: list[RemoteActionWorker] = []
        self._body_workers: list[BodyFetchWorker] = []
        self._fetching_body_ids: set[int] = set()
        self._status_items: dict[int, QTreeWidgetItem] = {}
        self._panel_account_id: int | None = None
        self._extra_limit = 0  # raised by the Load More button

        self.setWindowTitle("Unified")
        self.setWindowIcon(make_app_icon())
        self.resize(1200, 760)
        apply_white_titlebar(self)

        self._build_toolbar()
        self._build_body()
        self._build_tray()
        self.statusBar().showMessage("Ready")

        # Coalesced reload: many sync events -> at most ~1 reload per 700 ms.
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(700)
        self._reload_timer.timeout.connect(self._do_scheduled_reload)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.reload_email_list)

        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self.start_sync)
        self._apply_sync_interval()

        self.sync.progress.connect(self._on_account_progress)
        self.sync.state_changed.connect(self._on_sync_state_changed)
        self.sync.account_done.connect(self._on_account_done)
        self.sync.all_finished.connect(self._on_all_finished)

        self.reload_sidebar()
        self.reload_email_list()
        QTimer.singleShot(50, self._startup_integrity_check)
        if self.db.get_accounts():
            QTimer.singleShot(400, self.start_sync)

    def _startup_integrity_check(self) -> None:
        """Verify the local database and stored sign-ins; repair, never crash."""
        report = self.db.check_and_repair()
        if not report["ok"]:
            log.error("Database check found issues: %s",
                      "; ".join(report["problems"]))
            self.statusBar().showMessage(
                "Database check found issues - "
                + "; ".join(report["problems"])
            )
            return
        if report["problems"]:
            log.warning("Database check found issues: %s - repairing...",
                        "; ".join(report["problems"]))
            log.info("Database repaired: %s", "; ".join(report["repaired"]))
            self.statusBar().showMessage(
                "Database check found issues - repaired: "
                + "; ".join(report["repaired"])
            )
            self.reload_sidebar()
            self.reload_email_list()
        else:
            log.info("Database check passed (%s accounts, %s cached emails)",
                     len(self.db.get_accounts()),
                     f"{self.db.count_emails('inbox') + self.db.count_emails('sent') + self.db.count_emails('trash'):,}")

        # Stored sign-ins present? (No network call - just keyring presence.)
        from app.auth import secrets_store
        for account in self.db.get_accounts():
            kind = (secrets_store.KIND_GMAIL_TOKEN
                    if account["provider"] == "gmail"
                    else secrets_store.KIND_IMAP_PASSWORD)
            if not secrets_store.get_secret(kind, account["email"]):
                log.warning(
                    "Account %s: no stored sign-in found - remove and "
                    "re-add this account", account["id"],
                )

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

        self.console_btn = QPushButton("Console")
        self.console_btn.setCheckable(True)
        self.console_btn.toggled.connect(self._toggle_console)
        toolbar.addWidget(self.console_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search all accounts...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(320)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

    # --------------------------------------------------------------------- body

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- Sidebar
        self.sidebar = QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setRootIsDecorated(False)
        self.sidebar.setFixedWidth(230)
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
        self.email_list.setUniformRowHeights(True)  # fast scrolling on big lists
        self.email_list.itemSelectionChanged.connect(self._on_email_selected)
        self.email_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.email_list.customContextMenuRequested.connect(self._email_context_menu)

        # List page: the list plus a Load More button that appears whenever
        # the display limit hides messages (so nothing ever looks missing).
        list_page = QWidget()
        lp = QVBoxLayout(list_page)
        lp.setContentsMargins(0, 0, 0, 0)
        lp.setSpacing(4)
        self.load_more_btn = QPushButton("Load more")
        self.load_more_btn.setVisible(False)
        self.load_more_btn.clicked.connect(self._load_more)
        lp.addWidget(self.email_list, stretch=1)
        lp.addWidget(self.load_more_btn)

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(list_page)
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

        self.preview_body = HtmlMailView()

        pv.addWidget(self.preview_subject)
        pv.addWidget(self.preview_meta)
        pv.addLayout(actions_row)
        pv.addWidget(self.preview_body, stretch=1)
        splitter.addWidget(preview)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 4)
        splitter.setSizes([230, 620, 350])

        # -- Console under the main area (collapsible, hidden by default)
        self.console = ConsoleWidget()
        self.console.setVisible(False)

        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(splitter)
        vertical.addWidget(self.console)
        vertical.setStretchFactor(0, 4)
        vertical.setStretchFactor(1, 1)
        vertical.setSizes([560, 140])
        self.setCentralWidget(vertical)

    def _toggle_console(self, visible: bool) -> None:
        self.console.setVisible(visible)

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
        self.tray.setToolTip("Unified")
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
        self._status_items.clear()

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

            status_text = self._account_status_text(account)
            status_item = QTreeWidgetItem([f"      {status_text}"])
            status_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            status_item.setForeground(0, STATUS_GRAY)
            item.addChild(status_item)
            self._status_items[account["id"]] = status_item
            status_item.setHidden(not status_text)

        add_item = QTreeWidgetItem(["  + Add account..."])
        add_item.setData(0, Qt.ItemDataRole.UserRole, ("add", None))
        self.sidebar.addTopLevelItem(add_item)

        settings_item = QTreeWidgetItem(["Settings"])
        settings_item.setData(0, Qt.ItemDataRole.UserRole, ("settings", None))
        self.sidebar.addTopLevelItem(settings_item)
        self.sidebar.expandAll()

    def _account_status_text(self, account: dict) -> str:
        state = self.sync.status(account["id"])
        status = state["status"]
        if status == ST_SYNCING:
            phase = state.get("phase", PH_CONNECT)
            done, total = state.get("done", 0), state.get("total", 0)
            if total:
                return f"↻ {phase} {done:,}/{total:,}"
            if done:  # listing phase reports a running count
                return f"↻ {phase} ({done:,} found)"
            return f"↻ {phase}"
        if status == ST_WAITING:
            return "· Waiting"
        if status == ST_ERROR:
            result = state.get("result", {})
            reason = result.get("error", "unknown error")
            return f"✗ Failed: {reason[:60]}"
        if status == ST_PARTIAL:
            result = state.get("result", {})
            return (f"⚠ {result.get('local_total', 0):,}/"
                    f"{result.get('server_total', 0):,}"
                    f" - {result.get('failed', 0)} failed, Refresh to retry")
        if status == ST_DONE:
            result = state.get("result", {})
            return (f"✓ Complete - {result.get('local_total', 0):,}/"
                    f"{result.get('server_total', 0):,} verified")
        if account["initial_sync_completed"]:
            return "✓ Synced"
        return ""

    def _update_status_item(self, account_id: int) -> None:
        item = self._status_items.get(account_id)
        if item is None:
            return
        account = self.db.get_account(account_id)
        if account is None:
            return
        text = self._account_status_text(account)
        item.setText(0, f"      {text}")
        item.setHidden(not text)

    def _on_sidebar_clicked(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, value = data
        if kind in ("view", "account"):
            self._extra_limit = 0  # each view starts at the base display limit
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
        self._update_search_placeholder()
        self.reload_email_list()

    def _update_search_placeholder(self) -> None:
        """Search always scopes to whatever is currently shown: a single
        account's inbox, or every account combined."""
        text = "Search inbox..." if self.current_account_id is not None \
            else "Search all accounts..."
        self.search_edit.setPlaceholderText(text)

    # --------------------------------------------------------------- email list

    def _schedule_reload(self) -> None:
        if not self._reload_timer.isActive():
            self._reload_timer.start()

    def _do_scheduled_reload(self) -> None:
        self.reload_sidebar()
        self.reload_email_list()

    def _on_search_changed(self) -> None:
        self._extra_limit = 0
        self._search_timer.start()

    def _load_more(self) -> None:
        self._extra_limit += int(self.settings.get("messages_shown"))
        self.reload_email_list()

    def reload_email_list(self) -> None:
        search = self.search_edit.text().strip()
        starred = self.current_view == "starred"
        folder = self.current_view if not starred else "inbox"
        limit = int(self.settings.get("messages_shown")) + self._extra_limit
        emails = self.db.list_emails(
            folder=folder,
            account_id=self.current_account_id,
            starred_only=starred,
            search=search,
            limit=limit,
        )
        total = self.db.count_emails(
            folder=folder,
            account_id=self.current_account_id,
            starred_only=starred,
            search=search,
        )

        self.email_list.setUpdatesEnabled(False)
        self.email_list.blockSignals(True)
        self.email_list.clear()
        bold = QFont()
        bold.setBold(True)

        items = []
        selected_item = None
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
            items.append(item)
            if msg["id"] == self.current_email_id:
                selected_item = item

        self.email_list.addTopLevelItems(items)
        if selected_item is not None:
            self.email_list.setCurrentItem(selected_item)
        self.email_list.blockSignals(False)
        self.email_list.setUpdatesEnabled(True)

        shown = len(emails)
        if total > shown:
            self.statusBar().showMessage(
                f"Showing newest {shown:,} of {total:,} emails"
                " - use Load more or search to reach older mail"
            )
            self.load_more_btn.setText(
                f"Load more  (showing {shown:,} of {total:,} emails)"
            )
            self.load_more_btn.setVisible(True)
        else:
            self.statusBar().showMessage(
                f"{total:,} message{'s' if total != 1 else ''}"
            )
            self.load_more_btn.setVisible(False)
        self._refresh_center_page(shown)

    def _refresh_center_page(self, email_count: int) -> None:
        """Panel instead of list only while a pending account has no rows yet.

        As soon as metadata lands, the live list is shown so the app stays
        usable during sync.
        """
        accounts = self.db.get_accounts()
        account = None
        if self.current_account_id is not None:
            current = next(
                (a for a in accounts if a["id"] == self.current_account_id), None
            )
            if (current and email_count == 0
                    and self.sync.is_account_pending(current["id"])):
                account = current
        elif (
            email_count == 0
            and self.current_view == "inbox"
            and not self.search_edit.text().strip()
        ):
            account = next(
                (a for a in accounts if self.sync.is_account_pending(a["id"])),
                None,
            )
        if account is None:
            self._panel_account_id = None
            self.center_stack.setCurrentIndex(0)
            return
        self._panel_account_id = account["id"]
        self._update_sync_panel(account)
        self.center_stack.setCurrentIndex(1)

    def _update_sync_panel(self, account: dict) -> None:
        self.sync_account_label.setText(account["email"])
        state = self.sync.status(account["id"])
        if state["status"] == ST_SYNCING:
            phase = state.get("phase", PH_CONNECT)
            done, total = state.get("done", 0), state.get("total", 0)
            friendly = PHASE_TEXT.get(phase, phase + "...")
            if account["provider"] == "gmail" and phase == PH_CONNECT:
                friendly = "Connecting Gmail..."
            self.sync_status_label.setText(friendly)
            if total:
                self.sync_detail_label.setText(f"{phase}  {done:,} / {total:,}")
                self.sync_bar.setRange(0, total)
                self.sync_bar.setValue(done)
            elif done:
                self.sync_detail_label.setText(f"{phase}: {done:,} found")
                self.sync_bar.setRange(0, 0)
            else:
                self.sync_detail_label.setText(phase)
                self.sync_bar.setRange(0, 0)
        elif state["status"] == ST_WAITING:
            self.sync_status_label.setText("Waiting to sync...")
            self.sync_detail_label.setText(
                "Another account is currently syncing"
            )
            self.sync_bar.setRange(0, 0)
        else:
            self.sync_status_label.setText("Loading mailbox...")
            self.sync_detail_label.setText("Preparing mailbox...")
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

    def _show_preview_placeholder(self, title: str, body: str) -> None:
        self.preview_subject.setText(title)
        self.preview_meta.setText("")
        self.preview_body.set_email_text(body)
        self.star_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)

    def _on_email_selected(self) -> None:
        items = self.email_list.selectedItems()
        if not items:
            return
        email_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        msg = self.db.get_email(email_id)
        if not msg:
            # Deleted under us (pruned by sync) - explain, never blank.
            self._show_preview_placeholder(
                "Message unavailable",
                "This message is no longer available.\n\n"
                "It may have been deleted or moved on the server.",
            )
            return
        self.current_email_id = email_id

        self.preview_subject.setText(msg["subject"] or "(no subject)")
        sender = msg["sender_name"] or msg["sender_email"]
        meta = (
            f"From: {html.escape(sender)} &lt;{html.escape(msg['sender_email'])}&gt;<br>"
            f"To: {html.escape(msg['recipients'] or '')}<br>"
            f"Account: {html.escape(msg['account_email'])}"
            f" &nbsp;|&nbsp; {self._format_time(msg['date_ts'])}"
        )
        if msg["has_attachments"]:
            meta += " &nbsp;|&nbsp; has attachments"
        self.preview_meta.setText(meta)
        self.star_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.star_btn.setText("Unstar" if msg["is_starred"] else "Star")

        if msg["body_fetched"]:
            self._render_body(msg)
        else:
            self.preview_body.set_email_text(
                "Loading email...\n\nDownloading message content..."
            )
            self._start_body_fetch(msg)

        if not msg["is_read"]:
            self.db.set_read(email_id, True)
            self._remote_action(msg, "read", True)
            self._schedule_reload()

    def _render_body(self, msg: dict) -> None:
        if msg["body_html"]:
            self.preview_body.set_email_html(msg["body_html"])
        elif msg["body_text"]:
            self.preview_body.set_email_text(msg["body_text"])
        elif msg["snippet"]:
            self.preview_body.set_email_text(msg["snippet"])
        else:
            self.preview_body.set_email_text("(This message has no content.)")

    def _start_body_fetch(self, msg: dict) -> None:
        if msg["id"] in self._fetching_body_ids:
            return  # rapid re-click on the same email: one fetch is enough
        account = self.db.get_account(msg["account_id"])
        if account is None:
            self._show_preview_placeholder(
                "Message unavailable", "The account for this message was removed."
            )
            return
        self._fetching_body_ids.add(msg["id"])
        worker = BodyFetchWorker(self.db.path, msg, account, self)
        worker.loaded.connect(self._on_body_loaded)
        worker.failed.connect(self._on_body_failed)
        worker.finished.connect(
            lambda w=worker, mid=msg["id"]: (
                self._fetching_body_ids.discard(mid),
                w in self._body_workers and self._body_workers.remove(w),
            )
        )
        self._body_workers.append(worker)
        worker.start()

    def _on_body_loaded(self, email_id: int) -> None:
        if email_id != self.current_email_id:
            return  # user moved on; body is cached for next time
        msg = self.db.get_email(email_id)
        if msg is None:
            return
        self.preview_body.set_email_text("Rendering preview...")
        self._render_body(msg)
        if msg["has_attachments"]:
            # Attachment flag becomes known only after the full fetch.
            current = self.preview_meta.text()
            if "has attachments" not in current:
                self.preview_meta.setText(current + " &nbsp;|&nbsp; has attachments")

    def _on_body_failed(self, email_id: int, reason: str) -> None:
        if email_id != self.current_email_id:
            return
        self.preview_body.set_email_text(
            "Could not load this message.\n\n"
            f"{reason}\n\nSelect the message again to retry."
        )

    # ------------------------------------------------------------------ actions

    def _remote_action(self, msg: dict, action: str, value: bool = True) -> None:
        account = self.db.get_account(msg["account_id"])
        if not account:
            return
        worker = RemoteActionWorker(account, action, msg["uid"], msg["folder"], value)
        worker.failed.connect(
            lambda err: self.statusBar().showMessage(f"Server update failed: {err}")
        )
        worker.finished.connect(
            lambda w=worker: w in self._action_workers
            and self._action_workers.remove(w)
        )
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
        self._schedule_reload()

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
        self._show_preview_placeholder("Select an email", "")
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
        accounts = self.db.get_accounts()
        if not accounts:
            self.statusBar().showMessage("Add an account to start syncing")
            return
        self.sync.request_sync([a["id"] for a in accounts])

    def _on_account_progress(
        self, account_id: int, phase: str, done: int, total: int
    ) -> None:
        self._update_status_item(account_id)
        if self._panel_account_id == account_id:
            account = self.db.get_account(account_id)
            if account:
                self._update_sync_panel(account)
        self._schedule_reload()

    def _on_sync_state_changed(self, account_id: int) -> None:
        self._update_status_item(account_id)
        if self._panel_account_id == account_id:
            account = self.db.get_account(account_id)
            if account:
                self._update_sync_panel(account)

    def _on_account_done(self, account_id: int, result: dict) -> None:
        account = self.db.get_account(account_id)
        email = account["email"] if account else f"account {account_id}"
        if result.get("error"):
            self.statusBar().showMessage(f"Sync error - {email}: {result['error']}")
        elif result.get("cancelled"):
            pass
        elif result.get("failed"):
            self.statusBar().showMessage(
                f"Sync completed with issues - {email}: "
                f"{result['local_total']:,}/{result['server_total']:,} downloaded, "
                f"{result['failed']:,} failed. Press Refresh to retry."
            )
        elif result.get("was_initial"):
            self.statusBar().showMessage(
                f"Mailbox ready - {email}: "
                f"{result['local_total']:,} messages verified in local cache"
            )
        self._schedule_reload()

    def _on_all_finished(self, notify_count: int) -> None:
        self._schedule_reload()
        if notify_count:
            plural = "s" if notify_count != 1 else ""
            self.statusBar().showMessage(
                f"Sync complete - {notify_count} new message{plural}"
            )
        self.notifier.notify_new_mail(notify_count)

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
        # Non-modal so a running Google sign-in or sync never blocks this.
        if self._account_dialog is not None:
            try:
                self._account_dialog.raise_()
                self._account_dialog.activateWindow()
                return
            except RuntimeError:
                self._account_dialog = None  # stale reference to deleted dialog
        dialog = AccountDialog(self.manager, self)
        dialog.finished.connect(lambda _: self._on_account_dialog_done(dialog))
        self._account_dialog = dialog
        dialog.show()

    def _on_account_dialog_done(self, dialog: AccountDialog) -> None:
        self._account_dialog = None
        account = dialog.added_account
        dialog.deleteLater()
        if account:
            # Jump to the new account; it queues immediately even if other
            # accounts are mid-sync (shows Waiting/progress, never empty).
            self.current_view = "inbox"
            self.current_account_id = account["id"]
            self._update_search_placeholder()
            self.reload_sidebar()
            self.reload_email_list()
            self.sync.request_sync([account["id"]])

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.manager, self)
        if dialog.exec():
            self._apply_sync_interval()
            if dialog.accounts_changed:
                remaining = {a["id"] for a in self.db.get_accounts()}
                for aid in self.sync.known_account_ids():
                    if aid not in remaining:
                        self.sync.forget_account(aid)
                self.reload_sidebar()
                self.reload_email_list()

    # ------------------------------------------------------------------- close

    def closeEvent(self, event) -> None:
        self._sync_timer.stop()
        self._reload_timer.stop()
        if self._account_dialog is not None:
            self._account_dialog.shutdown()
            self._account_dialog.close()
        self.sync.shutdown()
        for worker in list(self._body_workers):
            worker.wait(2000)
        for worker in list(self._action_workers):
            worker.wait(1000)
        self.console.detach()
        self.tray.hide()
        event.accept()

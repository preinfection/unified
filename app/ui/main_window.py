"""The application shell.

Three panes under one command bar, and a status strip along the bottom:

    ┌─────────────────────────────────────────────────────────────┐
    │ ☰  Unified   [Compose] ⟳          [ search ]      ☾  ⌘  ⋯   │
    ├──────────┬───────────────────────┬──────────────────────────┤
    │ Mailboxes│ Inbox · 1,284 msgs    │ Reply  Forward   ★  ⋯  🗑 │
    │  Inbox 37│ ──────────────────────│ ─────────────────────────│
    │  Starred │ ● Sender      14:32   │ Subject                  │
    │  Sent    │   Subject         📎  │ [AV] Sender    Tue 09:14 │
    │  Trash   │   Preview text…       │      To: …               │
    │ Accounts │ ────────────────────  │ ─────────────────────────│
    │  a@x.com │   Sender      Mon     │ message body             │
    └──────────┴───────────────────────┴──────────────────────────┘

Everything below this docstring is either wiring or the two behaviors
that genuinely belong to the shell rather than to a component:

**Scope.** The app has exactly one piece of view state - a mailbox, an
optional account filter, an optional unread filter, and a search string -
and every surface reads it from the same place. That is why the list
header can state the scope in words, why search knows what it is
searching, and why switching account keeps you in the mailbox you were
already in.

**Shape.** The window rearranges itself at two real widths (not imported
web breakpoints - each one is the width below which a pane can no longer
show its content): the sidebar becomes an icon rail, then the reading
pane takes over the list's space entirely, with a Back button, the way a
narrow mail window has to work.

Threading rules, unchanged from before the redesign:
- All network work (sync, body fetch, remote flag updates) runs on QThreads.
- UI reloads triggered by sync signals are coalesced through a single-shot
  timer so heavy sync activity cannot cause reload storms.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import QByteArray, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLabel,
    QMainWindow,
    QMenu,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__, config
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
    OlderFetchWorker,
    RemoteActionWorker,
    RemoteSearchWorker,
    SyncManager,
)
from app.ui import theme as t
from app.ui.account_dialog import AccountDialog
from app.ui.design import motion
from app.ui.components.buttons import Button, refresh_button_icons
from app.ui.components.command_bar import CommandBar
from app.ui.components.dialog import confirm, notify
from app.ui.components.email_list import EmailListView, format_full_time, format_time
from app.ui.components.list_header import ListHeader
from app.ui.components.reader import ReaderPane
from app.ui.components.sidebar import SidebarWidget
from app.ui.components.states import (
    EmptyState,
    ErrorState,
    LoadingState,
    SkeletonList,
    WelcomeState,
)
from app.ui.components.toast import ToastHost
from app.ui.compose_dialog import (
    ComposeDialog,
    forward_subject,
    quote_body,
    reply_subject,
)
from app.ui.console import ConsoleWidget
from app.ui.icons import make_app_icon
from app.ui.native_theme import apply_dark_titlebar
from app.ui.settings_dialog import SettingsDialog
from app.ui.svg_icon import themed

log = logging.getLogger(__name__)

# Friendly first-launch wording for each sync phase (loading-state display)
PHASE_TEXT = {
    PH_CONNECT: "Connecting to your account",
    PH_LIST: "Downloading the message list",
    PH_META: "Downloading the message list",
    PH_BODIES: "Downloading message content",
    PH_INDEX: "Preparing your mailbox",
    PH_VERIFY: "Preparing your mailbox",
}

VIEW_TITLES = {
    "inbox": "Inbox",
    "starred": "Starred",
    "sent": "Sent",
    "trash": "Trash",
}

# Below this length a search string is treated as mid-typing: the local
# cache is still searched live, but providers are not asked (a server-side
# search per keystroke would be abusive and slow).
_REMOTE_SEARCH_MIN_CHARS = 3

# Center-pane pages, in the order they are added to the stack.
PAGE_LIST, PAGE_LOADING, PAGE_EMPTY, PAGE_ERROR, PAGE_WELCOME = range(5)


def _decode_attachments(msg: dict) -> list[dict]:
    """Attachment metadata is cached as a JSON string. A row written by an
    older build (or a corrupted value) must degrade to "no per-file
    metadata", never break opening the message."""
    raw = msg.get("attachments") or ""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


# Sync status -> the color key StatusDot/theme.status_color understands.
_STATUS_KEY = {
    ST_SYNCING: "syncing",
    ST_WAITING: "waiting",
    ST_ERROR: "error",
    ST_PARTIAL: "partial",
    ST_DONE: "done",
}


class MainWindow(QMainWindow):
    def __init__(self, db: Database, settings: config.Settings):
        super().__init__()
        self.db = db
        self.settings = settings
        self.manager = AccountManager(db)
        self.sync = SyncManager(db.path, self)

        # ---- the one piece of view state, read by every surface
        self.current_view = "inbox"          # inbox | starred | sent | trash
        self.current_account_id: int | None = None
        self.current_email_id: int | None = None
        self.unread_only = False

        self._account_dialog: AccountDialog | None = None
        self._compose_dialogs: list[ComposeDialog] = []
        self._action_workers: list[RemoteActionWorker] = []
        self._body_workers: list[BodyFetchWorker] = []
        self._fetching_body_ids: set[int] = set()
        self._panel_account_id: int | None = None
        self._extra_limit = 0
        self._stacked_mode = False
        self._reading = False
        # Which account ids the sidebar was last built with, so a
        # sync-progress-driven reload (roughly every 700ms while syncing)
        # can skip rebuilding every AccountItem when the set is unchanged.
        self._known_account_ids: set[int] = set()
        # Which accounts produced a sync event since the last reload - lets
        # a debounced reload skip re-querying the list when the view on
        # screen is scoped to an account that had nothing happen.
        self._dirty_account_ids: set[int] = set()
        self._dirty_reload_all = False
        self._older_workers: list[OlderFetchWorker] = []
        self._older_fetch_ids: set[int] = set()
        self._search_workers: list[RemoteSearchWorker] = []
        self._remote_searched: set[str] = set()

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon())
        self.resize(1360, 860)
        self.setMinimumSize(720, 520)

        self._apply_saved_appearance()
        self._build_shell()
        self._build_status_bar()
        self._build_tray()
        self._install_shortcuts()
        self.toasts = ToastHost(self)
        apply_dark_titlebar(self)

        # Coalesced reload: many sync events -> at most ~1 reload per 700ms.
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(700)
        self._reload_timer.timeout.connect(self._do_scheduled_reload)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._run_search)

        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self.start_sync)
        self._apply_sync_interval()

        self.sync.progress.connect(self._on_account_progress)
        self.sync.state_changed.connect(self._on_sync_state_changed)
        self.sync.account_done.connect(self._on_account_done)
        self.sync.all_finished.connect(self._on_all_finished)
        t.theme_manager.changed.connect(self._on_theme_changed)

        self.reload_sidebar()
        self.reload_email_list()
        QTimer.singleShot(50, self._startup_integrity_check)
        if self.db.get_accounts():
            QTimer.singleShot(400, self.start_sync)

    # ---------------------------------------------------------------- open

    def open_window(self) -> None:
        """Show the window the way the user last left it.

        Maximised by default: a mail client is a fill-the-screen tool, and
        a three-pane layout in a 1360px window on a large display wastes
        most of it. The restored (un-maximised) size is remembered too, so
        pressing restore-down gives back the size that was actually being
        used rather than a hard-coded default.
        """
        geometry = self.settings.get("window_geometry")
        if geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
            except (ValueError, TypeError):
                pass
        if bool(self.settings.get("start_maximized", True)):
            self.showMaximized()
        else:
            self.show()

    def _remember_geometry(self) -> None:
        # saveGeometry() records the restored size and position even while
        # maximised, which is exactly what restore-down should return to.
        self.settings.set(
            "window_geometry",
            bytes(self.saveGeometry().toBase64()).decode("ascii"),
        )
        self.settings.set("start_maximized", self.isMaximized())

    # ------------------------------------------------------------ appearance

    def _apply_saved_appearance(self) -> None:
        mode = str(self.settings.get("theme_mode") or "system")
        density = str(self.settings.get("list_density") or t.DENSITY_DEFAULT)
        motion_mode = str(self.settings.get("motion_mode") or "system")
        if mode in t.MODES:
            t.theme_manager.set_mode(mode)
        if density in t.DENSITY_METRICS:
            t.theme_manager.set_density(density)
        if motion_mode in t.MOTION_MODES:
            t.theme_manager.set_motion_mode(motion_mode)

    def _on_theme_changed(self) -> None:
        """Rasterized icons do not follow a palette swap on their own, and
        the window caption is drawn by the OS - both need a nudge."""
        apply_dark_titlebar(self)
        refresh_button_icons(self)
        for widget in (self.toolbar, self.sidebar, self.list_header,
                       self.preview, self.welcome_state):
            refresh = getattr(widget, "refresh_icons", None) or getattr(
                widget, "refresh_icon", None
            )
            if callable(refresh):
                refresh()
        self.email_list.viewport().update()

    # ----------------------------------------------------------------- shell

    def _build_shell(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toolbar = CommandBar()
        self.toolbar.compose_clicked.connect(self.open_compose)
        self.toolbar.refresh_clicked.connect(self.start_sync)
        self.toolbar.console_toggled.connect(self._toggle_console)
        self.toolbar.search_changed.connect(self._on_search_changed)
        self.toolbar.search_escaped.connect(self._on_search_escaped)
        self.toolbar.settings_requested.connect(self.open_settings)
        self.toolbar.add_account_requested.connect(self.open_add_account)
        self.toolbar.theme_requested.connect(self._set_theme_mode)
        self.toolbar.density_requested.connect(self._set_density)
        self.toolbar.sidebar_toggled.connect(self._toggle_sidebar)
        self.toolbar.about_requested.connect(self._show_about)
        layout.addWidget(self.toolbar)

        self.sidebar = SidebarWidget()
        self.sidebar.view_selected.connect(self._on_view_selected)
        self.sidebar.account_selected.connect(self._on_account_selected)
        self.sidebar.add_account_requested.connect(self.open_add_account)
        self.sidebar.settings_requested.connect(self.open_settings)

        self.panes = QSplitter(Qt.Orientation.Horizontal)
        self.panes.setChildrenCollapsible(False)
        self.panes.setHandleWidth(1)
        self.panes.setAccessibleName("Mailbox")
        self.panes.addWidget(self.sidebar)
        self.panes.addWidget(self._build_list_pane())
        self.panes.addWidget(self._build_reader_pane())
        self.panes.setStretchFactor(0, 0)
        self.panes.setStretchFactor(1, 3)
        self.panes.setStretchFactor(2, 5)
        self.panes.setSizes([t.SIDEBAR_WIDTH, t.LIST_WIDTH_DEFAULT, 640])

        self.console = ConsoleWidget()
        self.console.setVisible(False)
        self._vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self._vertical_splitter.setHandleWidth(1)
        self._vertical_splitter.addWidget(self.panes)
        self._vertical_splitter.addWidget(self.console)
        self._vertical_splitter.setStretchFactor(0, 5)
        self._vertical_splitter.setStretchFactor(1, 1)
        # The console starts hidden, so it must start at zero height: a
        # QSplitter reserves proportional space for a child regardless of
        # that child's visibility, and a nonzero size here would silently
        # steal that much height from the panes above.
        self._vertical_splitter.setSizes([1, 0])
        layout.addWidget(self._vertical_splitter, stretch=1)

        self.setCentralWidget(root)
        # Tab order follows the reading order of the window rather than
        # the order the widgets happened to be constructed in.
        self.setTabOrder(self.toolbar.search_edit, self.sidebar)
        self.setTabOrder(self.sidebar, self.email_list)
        self.setTabOrder(self.email_list, self.preview)

    def _build_list_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("listPane")
        pane.setAccessibleName("Message list")
        pane.setMinimumWidth(t.LIST_WIDTH_MIN)
        column = QVBoxLayout(pane)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        self.list_header = ListHeader()
        self.list_header.unread_filter_toggled.connect(self._set_unread_only)
        self.list_header.select_all_read_requested.connect(self._mark_all_read)
        self.list_header.density_requested.connect(self._set_density)
        column.addWidget(self.list_header)

        self.email_list = EmailListView()
        self.email_list.email_selected.connect(self._on_email_selected)
        self.email_list.email_activated.connect(self._on_email_activated)
        self.email_list.context_menu_requested.connect(self._on_email_context_menu)
        self.email_list.reached_end.connect(self._on_list_end_reached)

        list_page = QWidget()
        page_layout = QVBoxLayout(list_page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(self.email_list, stretch=1)

        # Paging as a quiet footer rather than a button parked in the
        # layout at all times: it appears only when more messages exist,
        # and scrolling to the end triggers it anyway.
        self.load_more_btn = Button("Load more", variant="subtle", size="sm")
        self.load_more_btn.setVisible(False)
        self.load_more_btn.clicked.connect(self._load_more)
        page_layout.addWidget(self.load_more_btn)

        self.loading_state = LoadingState()
        self.empty_state = EmptyState()
        self.error_state = ErrorState()
        self.skeleton = SkeletonList()
        self.welcome_state = WelcomeState()
        self.welcome_state.provider_chosen.connect(self._start_onboarding)

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(list_page)
        self.center_stack.addWidget(self.loading_state)
        self.center_stack.addWidget(self.empty_state)
        self.center_stack.addWidget(self.error_state)
        self.center_stack.addWidget(self.welcome_state)
        column.addWidget(self.center_stack, stretch=1)
        return pane

    def _build_reader_pane(self) -> QWidget:
        self.preview = ReaderPane()
        self.preview.setAccessibleName("Reading pane")
        self.preview.star_clicked.connect(self._toggle_star)
        self.preview.delete_clicked.connect(self._delete_current)
        self.preview.reply_clicked.connect(lambda: self._open_reply(all_recipients=False))
        self.preview.reply_all_clicked.connect(lambda: self._open_reply(all_recipients=True))
        self.preview.forward_clicked.connect(self._open_forward)
        self.preview.mark_unread_clicked.connect(self._mark_current_unread)
        self.preview.back_clicked.connect(self._back_to_list)
        return self.preview

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(True)
        self._status_label = QLabel("Ready")
        self._status_label.setFont(t.make_font("caption"))
        bar.addWidget(self._status_label, 1)
        self._sync_label = QLabel("")
        self._sync_label.setFont(t.make_font("caption"))
        bar.addPermanentWidget(self._sync_label)

    def _set_status(self, text: str) -> None:
        """One status line, in one widget.

        QStatusBar.showMessage() paints a temporary message *over* the
        permanent widgets rather than replacing them, so using both means
        two strings drawn on top of each other in the corner.
        """
        self._status_label.setText(text)

    # ------------------------------------------------------------ shortcuts

    def _install_shortcuts(self) -> None:
        """Keyboard-first, the way a mail client is actually used. Every
        one of these is also reachable by pointer; none is the only route
        to its action."""
        bindings = [
            ("Ctrl+N", self.open_compose),
            ("Ctrl+F", self.toolbar.focus_search),
            ("/", self.toolbar.focus_search),
            ("F5", self.start_sync),
            ("Ctrl+R", self.start_sync),
            ("Ctrl+B", self._toggle_sidebar),
            ("Ctrl+,", self.open_settings),
            ("Ctrl+`", lambda: self.toolbar.console_button.toggle()),
            ("Ctrl+Shift+A", self.open_add_account),
            ("Del", self._delete_current),
            ("S", self._toggle_star),
            ("U", self._mark_current_unread),
            ("R", lambda: self._open_reply(all_recipients=False)),
            ("Shift+R", lambda: self._open_reply(all_recipients=True)),
            ("F", self._open_forward),
            ("Escape", self._on_escape),
        ]
        for index, view in enumerate(("inbox", "starred", "sent", "trash"), start=1):
            bindings.append((f"Ctrl+{index}", lambda v=view: self._select_view(v)))
        for sequence, handler in bindings:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(handler)

    def _on_escape(self) -> None:
        if self.toolbar.search_text():
            self.toolbar.search_edit.clear()
            self.email_list.setFocus()
            return
        if self._stacked_mode and self._reading:
            self._back_to_list()

    # ----------------------------------------------------------- responsive

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_layout_for_width(self.width())

    def _apply_layout_for_width(self, width: int) -> None:
        """Two real thresholds, each the point at which a pane stops being
        able to show its content rather than a number copied from CSS."""
        collapse = width < t.BREAKPOINT_COLLAPSE_SIDEBAR
        if not self._user_expanded_sidebar:
            self.sidebar.set_collapsed(collapse)
        self.toolbar.set_compact(width < t.BREAKPOINT_COLLAPSE_SIDEBAR)

        stacked = width < t.BREAKPOINT_STACK_READER
        if stacked != self._stacked_mode:
            self._stacked_mode = stacked
            self.preview.set_back_visible(stacked)
            self._apply_stacked_visibility()
        # The reader decides its own compact state from its own width -
        # see ReaderPane.resizeEvent.

    _user_expanded_sidebar = False

    def _apply_stacked_visibility(self) -> None:
        """In stacked mode only one of list/reader is on screen at a time -
        two 300px panes side by side show nothing useful in either."""
        if not self._stacked_mode:
            self.panes.widget(1).setVisible(True)
            self.preview.setVisible(True)
            return
        incoming = self.preview if self._reading else self.panes.widget(1)
        self.panes.widget(1).setVisible(not self._reading)
        self.preview.setVisible(self._reading)
        self._slide_in(incoming, forward=self._reading)

    def _slide_in(self, pane, *, forward: bool) -> None:
        """Slide a pane in from the direction it is travelling from.

        Forward (list -> message) enters from the right; Back enters from
        the left. Same distance and duration either way, so the return
        journey retraces the outbound one.
        """
        duration = t.duration(motion.PAGE_SLIDE)
        if duration <= 0:
            return
        effect = QGraphicsOpacityEffect(pane)
        pane.setGraphicsEffect(effect)
        offset = motion.DISTANCE_BASE * (1 if forward else -1)
        origin = pane.pos()

        animation = QVariantAnimation(pane)
        animation.setDuration(duration)
        animation.setEasingCurve(motion.EASE_SMOOTH_OUT)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)

        def step(value):
            progress = float(value)
            effect.setOpacity(1.0 - progress)
            pane.move(origin.x() + int(offset * progress), origin.y())

        animation.valueChanged.connect(step)
        animation.finished.connect(lambda: pane.setGraphicsEffect(None))
        animation.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _back_to_list(self) -> None:
        self._reading = False
        self._apply_stacked_visibility()
        self.email_list.setFocus()

    def _toggle_sidebar(self) -> None:
        collapsed = not self.sidebar.is_collapsed
        self.sidebar.set_collapsed(collapsed)
        # Remember that this was a deliberate choice, so a later resize
        # does not silently undo it.
        self._user_expanded_sidebar = not collapsed and (
            self.width() < t.BREAKPOINT_COLLAPSE_SIDEBAR
        )

    def _toggle_console(self, visible: bool) -> None:
        self.console.setVisible(visible)
        total = sum(self._vertical_splitter.sizes()) or self.height()
        if visible:
            self._vertical_splitter.setSizes([max(1, total - 240), 240])
        else:
            self._vertical_splitter.setSizes([total, 0])

    # ---------------------------------------------------------------- tray

    def _build_tray(self) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon

        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        show_action = QAction("Open Unified", menu)
        show_action.triggered.connect(self._show_from_tray)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self.notifier = Notifier(self.tray, self.settings)

    def _on_tray_activated(self, reason) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon

        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()

    def _quit(self) -> None:
        self.tray.hide()
        from PySide6.QtWidgets import QApplication

        QApplication.quit()

    # ------------------------------------------------------------- startup

    def _startup_integrity_check(self) -> None:
        """Verify the local database and stored sign-ins; repair, never crash."""
        report = self.db.check_and_repair()
        if not report["ok"]:
            log.error("Database check found issues: %s",
                      "; ".join(report["problems"]))
            self._set_status("Database check found issues")
            self.toasts.show(
                "Database check found issues",
                "; ".join(report["problems"]), kind="error",
            )
            return
        if report["problems"]:
            log.warning("Database check found issues: %s - repairing...",
                        "; ".join(report["problems"]))
            log.info("Database repaired: %s", "; ".join(report["repaired"]))
            self._set_status("Database repaired - no mail was lost")
            self.toasts.show(
                "Database repaired", "; ".join(report["repaired"]), kind="warning",
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

    # ------------------------------------------------------------- sidebar

    def reload_sidebar(self) -> None:
        """Refresh counts and status without rebuilding the account rows
        unless the account set itself changed.

        Called on every debounced sync-progress reload (roughly every
        700ms while any account is syncing), so rebuilding every
        AccountItem each time would tear down and recreate the drawer's
        widgets in a loop for as long as sync runs - real wasted UI-thread
        work during exactly the window the app most needs to stay
        responsive.
        """
        counts = self.db.unread_counts()
        accounts = self.db.get_accounts()
        account_ids = {a["id"] for a in accounts}
        if account_ids != self._known_account_ids:
            self.sidebar.set_accounts(accounts, counts["per_account"])
            self._known_account_ids = account_ids
        else:
            self.sidebar.update_unread_counts(counts["per_account"])
        self.sidebar.set_inbox_count(counts["total"])
        self.sidebar.set_current(self.current_view, self.current_account_id)
        for account in accounts:
            self._update_account_status_display(account["id"])

    def _account_status(self, account: dict) -> tuple[str, str]:
        """Return (status_key, display_text) for the sidebar status dot."""
        state = self.sync.status(account["id"])
        status = state["status"]
        if status == ST_SYNCING:
            phase = state.get("phase", PH_CONNECT)
            done, total = state.get("done", 0), state.get("total", 0)
            if total:
                text = f"{phase} {done:,}/{total:,}"
            elif done:
                text = f"{phase} ({done:,} found)"
            else:
                text = phase
            return "syncing", text
        if status == ST_WAITING:
            return "waiting", "Waiting to sync"
        if status == ST_ERROR:
            reason = state.get("result", {}).get("error", "unknown error")
            return "error", f"Failed: {reason[:60]}"
        if status == ST_PARTIAL:
            result = state.get("result", {})
            return "partial", (
                f"{result.get('local_total', 0):,}/{result.get('server_total', 0):,}"
                f" - {result.get('failed', 0)} failed, Refresh to retry"
            )
        if status == ST_DONE:
            result = state.get("result", {})
            return "done", (
                f"Synced - {result.get('local_total', 0):,}/"
                f"{result.get('server_total', 0):,} verified"
            )
        if account["initial_sync_completed"]:
            return "done", ""
        return "idle", ""

    def _update_account_status_display(self, account_id: int) -> None:
        account = self.db.get_account(account_id)
        if account is None:
            return
        status_key, text = self._account_status(account)
        self.sidebar.update_account_status(account_id, status_key, text)

    # ------------------------------------------------------------ view state

    def _select_view(self, view: str) -> None:
        self.sidebar.set_current(view, None)
        self._on_view_selected(view)

    def _on_view_selected(self, view: str) -> None:
        self._extra_limit = 0
        self.current_view = view
        self.current_account_id = None
        self._refresh_scope()
        self.reload_email_list()

    def _on_account_selected(self, account_id: int) -> None:
        """An account is a *filter* on the mailbox you are already in -
        selecting one keeps the current mailbox rather than jumping you
        somewhere else, which is what made the old sidebar ambiguous."""
        self._extra_limit = 0
        if self.current_account_id == account_id:
            self.current_account_id = None  # clicking again clears the filter
            self.sidebar.set_current(self.current_view, None)
        else:
            self.current_account_id = account_id
        self._refresh_scope()
        self.reload_email_list()

    def _set_unread_only(self, enabled: bool) -> None:
        self.unread_only = enabled
        self._extra_limit = 0
        self.reload_email_list()

    def _set_density(self, density: str) -> None:
        t.theme_manager.set_density(density)
        self.settings.set("list_density", density)

    def _set_theme_mode(self, mode: str) -> None:
        t.theme_manager.set_mode(mode)
        self.settings.set("theme_mode", mode)
        self.toolbar.refresh_theme_icon()

    def _refresh_scope(self) -> None:
        """Everything that states 'where am I' updates from one place."""
        account = (
            self.db.get_account(self.current_account_id)
            if self.current_account_id is not None else None
        )
        title = VIEW_TITLES.get(self.current_view, "Mailbox")
        self.list_header.set_scope(title, account["email"] if account else None)
        self.toolbar.set_search_placeholder(
            f"Search {account['email']}" if account else "Search all accounts"
        )
        self.email_list.set_show_account(
            account is None and len(self.db.get_accounts()) > 1
        )

    # --------------------------------------------------------- email list

    def _schedule_reload(self, account_id: int | None = None) -> None:
        """Coalesce reloads into at most one per 700ms. `account_id`, when
        given, marks only that account as having new data - a debounced
        tick then skips re-querying the list if the view on screen is
        scoped to a *different* account, since nothing in it could have
        changed. Omitting it (user actions, end-of-round) always refreshes.
        """
        if account_id is not None:
            self._dirty_account_ids.add(account_id)
        else:
            self._dirty_reload_all = True
        if not self._reload_timer.isActive():
            self._reload_timer.start()

    def _do_scheduled_reload(self) -> None:
        dirty_ids = self._dirty_account_ids
        reload_all = self._dirty_reload_all
        self._dirty_account_ids = set()
        self._dirty_reload_all = False
        self.reload_sidebar()
        if (reload_all or self.current_account_id is None
                or self.current_account_id in dirty_ids):
            self.reload_email_list()

    def _on_search_changed(self, _text: str) -> None:
        self._extra_limit = 0
        self._search_timer.start()

    def _on_search_escaped(self) -> None:
        self.email_list.setFocus()

    def _run_search(self) -> None:
        """Show local cache hits immediately, then - only if the query
        looks deliberate - ask each provider to search its own server for
        anything the cache never held. The visible list is never blocked
        on the network; remote hits land later and refresh it."""
        self.reload_email_list()
        query = self.toolbar.search_text()
        if len(query) < _REMOTE_SEARCH_MIN_CHARS:
            return
        if query in self._remote_searched:
            return  # the providers were already asked for exactly this
        self._remote_searched.add(query)
        self._start_remote_search(query)

    def _start_remote_search(self, query: str) -> None:
        folder = "inbox" if self.current_view == "starred" else self.current_view
        if folder not in ("inbox", "sent", "trash"):
            return
        accounts = self.db.get_accounts()
        if self.current_account_id is not None:
            accounts = [a for a in accounts if a["id"] == self.current_account_id]
        if not accounts:
            return
        for account in accounts:
            worker = RemoteSearchWorker(self.db.path, account, query, folder, parent=self)
            worker.loaded.connect(
                lambda aid, added, q=query: self._on_remote_search_done(q, added)
            )
            worker.failed.connect(
                lambda aid, reason: log.info("Remote search unavailable: %s", reason)
            )
            worker.finished.connect(
                lambda w=worker: w in self._search_workers
                and self._search_workers.remove(w)
            )
            self._search_workers.append(worker)
            worker.start()
        self._set_status(f'Searching the server for "{query}"...')

    def _on_remote_search_done(self, query: str, added: int) -> None:
        if self.toolbar.search_text() != query:
            return  # the user has moved on from this query
        if added:
            self.reload_email_list()

    def _on_list_end_reached(self) -> None:
        if self.load_more_btn.isVisible():
            self._load_more()

    def _load_more(self) -> None:
        """Show the next page. Served from cache when possible; only when
        the cached rows run out does this reach the network for an older
        batch (see OlderFetchWorker) - paging is never a download."""
        page = int(self.settings.get("messages_shown"))
        self._extra_limit += page
        self.reload_email_list()

        # Cache boundary: the list came back short of what was asked for,
        # so there is nothing further cached to page into.
        requested = page + self._extra_limit
        if self.email_list.row_count() < requested:
            self._fetch_older_messages()

    def _fetch_older_messages(self) -> None:
        folder = "inbox" if self.current_view == "starred" else self.current_view
        if folder not in ("inbox", "sent", "trash"):
            return
        if self.current_account_id is not None:
            accounts = [a for a in self.db.get_accounts()
                        if a["id"] == self.current_account_id]
        else:
            accounts = self.db.get_accounts()

        for account in accounts:
            if account["id"] in self._older_fetch_ids:
                continue  # one older-fetch per account at a time
            self._older_fetch_ids.add(account["id"])
            worker = OlderFetchWorker(self.db.path, account, folder, parent=self)
            worker.loaded.connect(self._on_older_loaded)
            worker.failed.connect(self._on_older_failed)
            worker.finished.connect(
                lambda w=worker, aid=account["id"]: (
                    self._older_fetch_ids.discard(aid),
                    w in self._older_workers and self._older_workers.remove(w),
                )
            )
            self._older_workers.append(worker)
            worker.start()
        if self._older_fetch_ids:
            self._set_status("Loading older messages...")

    def _on_older_loaded(self, account_id: int, added: int) -> None:
        if added:
            self.reload_email_list()
        elif not self._older_fetch_ids:
            self._set_status("No older messages on the server")

    def _on_older_failed(self, account_id: int, reason: str) -> None:
        self._set_status("Could not load older messages")
        self.toasts.show("Could not load older messages", reason, kind="error")

    def reload_email_list(self) -> None:
        search = self.toolbar.search_text()
        starred = self.current_view == "starred"
        folder = self.current_view if not starred else "inbox"
        limit = int(self.settings.get("messages_shown")) + self._extra_limit
        emails = self.db.list_emails(
            folder=folder,
            account_id=self.current_account_id,
            starred_only=starred,
            search=search,
            limit=limit,
            unread_only=self.unread_only,
        )
        total = self.db.count_emails(
            folder=folder,
            account_id=self.current_account_id,
            starred_only=starred,
            search=search,
            unread_only=self.unread_only,
        )
        unread = self.db.count_emails(
            folder=folder,
            account_id=self.current_account_id,
            starred_only=starred,
            search=search,
            unread_only=True,
        )

        self.email_list.set_rows(emails, keep_selected_id=self.current_email_id)
        shown = len(emails)
        self.list_header.set_counts(shown, total, unread)
        self.list_header.set_unread_only(self.unread_only)

        if total > shown:
            self._set_status(f"Showing the newest {shown:,} of {total:,} messages")
            self.load_more_btn.setText(f"Load {min(total - shown, 100):,} more")
            self.load_more_btn.setVisible(True)
        else:
            self._set_status(f"{total:,} message{'s' if total != 1 else ''}")
            self.load_more_btn.setVisible(False)
        self._refresh_center_page(shown)

    def _refresh_center_page(self, email_count: int) -> None:
        """Alternatives to the live list, tried in order: a pending
        account's sync progress, then a designed empty state, then the
        list itself - so the app stays usable while a first sync runs."""
        accounts = self.db.get_accounts()
        if not accounts:
            # Nothing is connected yet, so the window has exactly one job.
            # Two empty states either side of a splitter is not onboarding.
            self._set_onboarding(True)
            self.center_stack.setCurrentIndex(PAGE_WELCOME)
            return
        self._set_onboarding(False)

        account = None
        if self.current_account_id is not None:
            current = next(
                (a for a in accounts if a["id"] == self.current_account_id), None
            )
            if (current and email_count == 0
                    and self.sync.is_account_pending(current["id"])):
                account = current
        elif (email_count == 0 and self.current_view == "inbox"
              and not self.toolbar.search_text()):
            account = next(
                (a for a in accounts if self.sync.is_account_pending(a["id"])), None
            )
        if account is not None:
            self._panel_account_id = account["id"]
            self._update_loading_state(account)
            self.center_stack.setCurrentIndex(PAGE_LOADING)
            return
        self._panel_account_id = None

        if email_count == 0:
            self._show_empty_state(has_accounts=bool(accounts))
            self.center_stack.setCurrentIndex(PAGE_EMPTY)
            return
        self.center_stack.setCurrentIndex(PAGE_LIST)

    def _set_onboarding(self, active: bool) -> None:
        """First run takes the whole content area.

        The reading pane and the list's own controls have nothing to act
        on before an account exists, and showing them anyway is what made
        an empty window read as a broken one.
        """
        if getattr(self, "_onboarding", None) == active:
            return
        self._onboarding = active
        self.preview.setVisible(not active and not self._stacked_mode
                                or (not active and self._reading))
        if not self._stacked_mode:
            self.preview.setVisible(not active)
        self.list_header.setVisible(not active)
        self.load_more_btn.setVisible(False)
        self.toolbar.compose_button.setEnabled(not active)
        self._set_status(
            "Connect an account to get started" if active
            else self._status_label.text()
        )

    def _start_onboarding(self, provider: int) -> None:
        """A provider was chosen on the welcome surface - open Add Account
        already on that choice rather than asking the same question
        again."""
        self.open_add_account()
        dialog = self._account_dialog
        if dialog is not None:
            dialog.select_provider(provider)

    def _show_empty_state(self, *, has_accounts: bool) -> None:
        search = self.toolbar.search_text()
        if not has_accounts:
            self.empty_state.set_state(
                icon="add_circle", title="Connect your first account",
                detail="Add a Gmail or IMAP account and Unified will bring "
                       "its mail into this mailbox.",
                action_text="Add account", on_action=self.open_add_account,
            )
        elif search:
            self.empty_state.set_state(
                icon="search", title="No messages match that search",
                detail=f'Nothing here matches "{search}". Try fewer words, or '
                       "check that you are searching the right account.",
                action_text="Clear search",
                on_action=self.toolbar.search_edit.clear,
            )
        elif self.unread_only:
            self.empty_state.set_state(
                icon="check_circle", title="Nothing unread",
                detail="You have read everything in this view.",
                action_text="Show all messages",
                on_action=lambda: self.list_header.unread_button.setChecked(False),
            )
        elif self.current_view == "starred":
            self.empty_state.set_state(
                icon="star_outline", title="No starred messages",
                detail="Star a message to keep it within reach here.",
            )
        elif self.current_view == "sent":
            self.empty_state.set_state(
                icon="sent", title="Nothing sent yet",
                detail="Messages you send from Unified appear here.",
                action_text="Write a message", on_action=self.open_compose,
            )
        elif self.current_view == "trash":
            self.empty_state.set_state(
                icon="trash", title="Trash is empty",
                detail="Deleted messages appear here.",
            )
        else:
            self.empty_state.set_state(
                icon="inbox", title="Inbox is empty",
                detail="New mail arrives here automatically.",
                action_text="Check for mail", on_action=self.start_sync,
            )

    def _update_loading_state(self, account: dict) -> None:
        state = self.sync.status(account["id"])
        if state["status"] == ST_SYNCING:
            phase = state.get("phase", PH_CONNECT)
            done, total = state.get("done", 0), state.get("total", 0)
            friendly = PHASE_TEXT.get(phase, phase)
            detail = f"{done:,} of {total:,}" if total else (
                f"{done:,} found so far" if done else "Working..."
            )
            self.loading_state.set_state(
                account["email"], friendly, detail, done, total
            )
        elif state["status"] == ST_WAITING:
            self.loading_state.set_state(
                account["email"], "Waiting to sync",
                "Another account is syncing first",
            )
        else:
            self.loading_state.set_state(
                account["email"], "Opening your mailbox", "Preparing messages",
            )

    # ------------------------------------------------------------- reading

    def _on_email_activated(self, email_id: int) -> None:
        self._on_email_selected(email_id)
        if self._stacked_mode:
            self._reading = True
            self._apply_stacked_visibility()

    def _on_email_selected(self, email_id: int) -> None:
        msg = self.db.get_email(email_id)
        if not msg:
            # Deleted under us (pruned by sync) - explain, never blank.
            self.preview.show_placeholder(
                "This message is no longer available",
                "It may have been deleted or moved on the server.",
            )
            return
        self.current_email_id = email_id
        if self._stacked_mode:
            self._reading = True
            self._apply_stacked_visibility()

        self.preview.show_message(
            subject=msg["subject"],
            sender_name=msg["sender_name"],
            sender_email=msg["sender_email"],
            recipients=msg["recipients"] or "",
            account_email=msg["account_email"],
            time_text=format_full_time(msg["date_ts"]),
            has_attachments=bool(msg["has_attachments"]),
            is_starred=bool(msg["is_starred"]),
            show_account=len(self.db.get_accounts()) > 1,
        )
        self.preview.set_attachments(_decode_attachments(msg))

        if msg["body_fetched"]:
            self._render_body(msg)
        else:
            self.preview.body.set_email_text("Downloading this message...")
            self._start_body_fetch(msg)

        if not msg["is_read"]:
            self.db.set_read(email_id, True)
            self._remote_action(msg, "read", True)
            self._schedule_reload()

    def _render_body(self, msg: dict) -> None:
        if msg["body_html"]:
            self.preview.body.set_email_html(msg["body_html"])
        elif msg["body_text"]:
            self.preview.body.set_email_text(msg["body_text"])
        elif msg["snippet"]:
            self.preview.body.set_email_text(msg["snippet"])
        else:
            self.preview.body.set_email_text("(This message has no content.)")

    def _start_body_fetch(self, msg: dict) -> None:
        if msg["id"] in self._fetching_body_ids:
            return  # rapid re-click on the same email: one fetch is enough
        account = self.db.get_account(msg["account_id"])
        if account is None:
            self.preview.show_placeholder(
                "This message is no longer available",
                "The account it belonged to has been removed.",
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
            return  # user moved on; the body is cached for next time
        msg = self.db.get_email(email_id)
        if msg is None:
            return
        self._render_body(msg)
        if msg["has_attachments"]:
            # The attachment flag becomes known only after the full fetch.
            self.preview.set_attachments(_decode_attachments(msg) or [{"name": "Attachment"}])

    def _on_body_failed(self, email_id: int, reason: str) -> None:
        if email_id != self.current_email_id:
            return
        self.preview.body.set_email_text(
            "This message could not be downloaded.\n\n"
            f"{reason}\n\nSelect it again to retry."
        )

    # ------------------------------------------------------------- actions

    def _remote_action(self, msg: dict, action: str, value: bool = True) -> None:
        account = self.db.get_account(msg["account_id"])
        if not account:
            return
        worker = RemoteActionWorker(account, action, msg["uid"], msg["folder"], value)
        worker.failed.connect(self._on_remote_action_failed)
        worker.finished.connect(
            lambda w=worker: w in self._action_workers
            and self._action_workers.remove(w)
        )
        self._action_workers.append(worker)
        worker.start()

    def _on_remote_action_failed(self, err: str) -> None:
        self._set_status("The server could not be updated")
        self.toasts.show(
            "Change not synced to the server",
            f"{err} - it is applied locally and will retry on the next sync.",
            kind="error",
        )

    def _toggle_star(self) -> None:
        if self.current_email_id is None:
            return
        msg = self.db.get_email(self.current_email_id)
        if not msg:
            return
        new_state = not msg["is_starred"]
        self.db.set_starred(self.current_email_id, new_state)
        self._remote_action(msg, "star", new_state)
        self.preview.set_starred(new_state)
        self._schedule_reload()

    def _mark_current_unread(self) -> None:
        if self.current_email_id is None:
            return
        msg = self.db.get_email(self.current_email_id)
        if not msg:
            return
        new_read = not msg["is_read"]
        self.db.set_read(self.current_email_id, new_read)
        self._remote_action(msg, "read", new_read)
        self._set_status("Marked as read" if new_read else "Marked as unread")
        self.reload_email_list()
        self.reload_sidebar()

    def _mark_all_read(self) -> None:
        starred = self.current_view == "starred"
        folder = self.current_view if not starred else "inbox"
        scope = "this account" if self.current_account_id is not None else "every account"
        if not confirm(
            self, "Mark everything as read?",
            f"All unread messages in {VIEW_TITLES.get(self.current_view, 'this view')} "
            f"for {scope} will be marked as read.",
            confirm_text="Mark as read",
        ):
            return
        changed = self.db.mark_all_read(
            folder=folder, account_id=self.current_account_id, starred_only=starred,
        )
        for row in changed:
            account = self.db.get_account(row["account_id"])
            if account:
                self._remote_action(
                    {"account_id": row["account_id"], "uid": row["uid"],
                     "folder": row["folder"]}, "read", True,
                )
        self._set_status(f"{len(changed):,} message(s) marked as read")
        self.reload_email_list()
        self.reload_sidebar()

    def _delete_current(self) -> None:
        if self.current_email_id is None:
            return
        msg = self.db.get_email(self.current_email_id)
        if not msg:
            return
        if msg["folder"] == "trash":
            self.toasts.show(
                "Already in Trash", "This message is already in the trash.",
                kind="info",
            )
            return
        self.db.move_to_trash(self.current_email_id)
        self._remote_action(msg, "trash")
        self.current_email_id = None
        self.preview.reset()
        if self._stacked_mode:
            self._back_to_list()
        self.reload_email_list()
        self.reload_sidebar()
        self.toasts.show(
            "Moved to Trash", msg["subject"] or "(no subject)", kind="info"
        )

    def _on_email_context_menu(self, email_id: int, global_pos) -> None:
        msg = self.db.get_email(email_id)
        if not msg:
            return
        menu = QMenu(self)
        mark = menu.addAction(
            themed("mail" if msg["is_read"] else "mail_open", t.ICON_SM, "default"),
            "Mark as unread" if msg["is_read"] else "Mark as read",
        )
        star = menu.addAction(
            themed("star_filled" if msg["is_starred"] else "star_outline",
                   t.ICON_SM, "star" if msg["is_starred"] else "default"),
            "Remove star" if msg["is_starred"] else "Star",
        )
        menu.addSeparator()
        reply = menu.addAction(themed("reply", t.ICON_SM, "default"), "Reply")
        forward = menu.addAction(themed("forward", t.ICON_SM, "default"), "Forward")
        menu.addSeparator()
        delete = menu.addAction(
            themed("trash", t.ICON_SM, "danger"), "Move to Trash"
        )

        chosen = menu.exec(global_pos)
        if chosen == mark:
            new_read = not msg["is_read"]
            self.db.set_read(email_id, new_read)
            self._remote_action(msg, "read", new_read)
        elif chosen == star:
            new_star = not msg["is_starred"]
            self.db.set_starred(email_id, new_star)
            self._remote_action(msg, "star", new_star)
        elif chosen == reply:
            self.current_email_id = email_id
            self._open_reply(all_recipients=False)
            return
        elif chosen == forward:
            self.current_email_id = email_id
            self._open_forward()
            return
        elif chosen == delete:
            self.current_email_id = email_id
            self._delete_current()
            return
        self.reload_email_list()
        self.reload_sidebar()

    # ---------------------------------------------------------------- sync

    def _apply_sync_interval(self) -> None:
        minutes = int(self.settings.get("sync_interval_minutes"))
        self._sync_timer.start(minutes * 60 * 1000)

    def start_sync(self) -> None:
        accounts = self.db.get_accounts()
        if not accounts:
            self._set_status("Add an account to start syncing")
            return
        self.sync.request_sync([a["id"] for a in accounts])

    def _on_account_progress(
        self, account_id: int, phase: str, done: int, total: int
    ) -> None:
        self._update_account_status_display(account_id)
        self._sync_label.setText(
            f"Syncing  {done:,}/{total:,}" if total else "Syncing..."
        )
        if self._panel_account_id == account_id:
            account = self.db.get_account(account_id)
            if account:
                self._update_loading_state(account)
        self._schedule_reload(account_id)

    def _on_sync_state_changed(self, account_id: int) -> None:
        self._update_account_status_display(account_id)
        if self._panel_account_id == account_id:
            account = self.db.get_account(account_id)
            if account:
                self._update_loading_state(account)

    def _on_account_done(self, account_id: int, result: dict) -> None:
        account = self.db.get_account(account_id)
        email = account["email"] if account else f"account {account_id}"
        if result.get("error"):
            self._set_status(f"Sync failed for {email}")
            self.toasts.show(f"Could not sync {email}", result["error"], kind="error")
        elif result.get("cancelled"):
            pass
        elif result.get("failed"):
            detail = (
                f"{result['local_total']:,} of {result['server_total']:,} downloaded, "
                f"{result['failed']:,} failed. Refresh to retry."
            )
            self._set_status(f"Sync finished with issues for {email}")
            self.toasts.show(f"Sync incomplete - {email}", detail, kind="warning")
        elif result.get("was_initial"):
            self._set_status(
                f"{email} is ready - {result['local_total']:,} messages cached"
            )
        self._schedule_reload(account_id)

    def _on_all_finished(self, notify_count: int) -> None:
        self._sync_label.setText("")
        self._schedule_reload()
        if notify_count:
            plural = "s" if notify_count != 1 else ""
            message = f"{notify_count} new message{plural}"
            self._set_status(f"Sync complete - {message}")
            if self.isActiveWindow():
                # The window already has focus, so a tray balloon would go
                # unseen - an in-app toast is the visible equivalent.
                self.toasts.show("New mail", message, kind="success")
        self.notifier.notify_new_mail(notify_count)

    # -------------------------------------------------------------- compose

    def open_compose(self, prefill: dict | None = None) -> None:
        accounts = self.db.get_accounts()
        if not accounts:
            notify(
                self, "No accounts yet",
                "Add an email account before writing a message.",
            )
            return
        dialog = ComposeDialog(accounts, self, prefill=prefill)
        dialog.sent.connect(lambda: self._on_message_sent())
        dialog.finished.connect(
            lambda _=0, d=dialog: (
                d in self._compose_dialogs and self._compose_dialogs.remove(d),
                d.deleteLater(),
            )
        )
        self._compose_dialogs.append(dialog)
        dialog.show()

    def _on_message_sent(self) -> None:
        self._set_status("Message sent")
        self.toasts.show("Message sent", "Your message is on its way.", kind="success")

    def _current_message(self) -> dict | None:
        if self.current_email_id is None:
            return None
        return self.db.get_email(self.current_email_id)

    def _open_reply(self, *, all_recipients: bool) -> None:
        msg = self._current_message()
        if msg is None:
            return
        account = self.db.get_account(msg["account_id"])
        sender = msg["sender_name"] or msg["sender_email"]
        cc = ""
        if all_recipients:
            others = [
                addr.strip() for addr in (msg["recipients"] or "").split(",")
                if addr.strip() and account
                and account["email"].lower() not in addr.lower()
            ]
            cc = ", ".join(others)
        self.open_compose({
            "title": "Reply",
            "to": msg["sender_email"],
            "cc": cc,
            "subject": reply_subject(msg["subject"]),
            "body": quote_body(sender, msg["date_ts"],
                               msg["body_text"] or msg["snippet"] or ""),
            "account": account,
            "focus": "body",
        })

    def _open_forward(self) -> None:
        msg = self._current_message()
        if msg is None:
            return
        account = self.db.get_account(msg["account_id"])
        sender = msg["sender_name"] or msg["sender_email"]
        self.open_compose({
            "title": "Forward",
            "to": "",
            "subject": forward_subject(msg["subject"]),
            "body": quote_body(sender, msg["date_ts"],
                               msg["body_text"] or msg["snippet"] or ""),
            "account": account,
        })

    # -------------------------------------------------------------- dialogs

    def open_add_account(self) -> None:
        # Non-modal so a running Google sign-in or sync never blocks this.
        if self._account_dialog is not None:
            try:
                self._account_dialog.raise_()
                self._account_dialog.activateWindow()
                return
            except RuntimeError:
                self._account_dialog = None  # stale reference to a deleted dialog
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
            self._refresh_scope()
            self.reload_sidebar()
            self.reload_email_list()
            self.sync.request_sync([account["id"]])
            self.toasts.show(
                "Account connected", f"Syncing {account['email']}...", kind="success"
            )

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.manager, self)
        if dialog.exec():
            self._apply_sync_interval()
            self.toolbar.refresh_theme_icon()
            self._apply_saved_appearance()
            if dialog.accounts_changed:
                remaining = {a["id"] for a in self.db.get_accounts()}
                for aid in self.sync.known_account_ids():
                    if aid not in remaining:
                        self.sync.forget_account(aid)
                if self.current_account_id not in remaining:
                    self.current_account_id = None
                self._refresh_scope()
                self.reload_sidebar()
                self.reload_email_list()

    def _show_about(self) -> None:
        notify(
            self, f"{APP_NAME} {__version__}",
            "A desktop mail client that keeps several accounts in one "
            "mailbox. Mail is cached locally and encrypted at rest; "
            "passwords and tokens live in the Windows Credential Manager.",
            detail=f"Data folder: {config.app_data_dir()}",
        )

    # ---------------------------------------------------------------- close

    def closeEvent(self, event) -> None:  # noqa: N802
        self._remember_geometry()
        self._sync_timer.stop()
        self._reload_timer.stop()
        if self._account_dialog is not None:
            self._account_dialog.shutdown()
            self._account_dialog.close()
        self.sync.shutdown()
        for worker in list(self._body_workers):
            worker.wait(2000)
        for worker in list(self._older_workers):
            worker.wait(2000)
        for worker in list(self._search_workers):
            worker.wait(2000)
        for worker in list(self._action_workers):
            worker.wait(1000)
        self.console.detach()
        self.tray.hide()
        event.accept()

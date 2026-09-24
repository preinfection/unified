"""Main window: sidebar / email list / preview, toolbar, console, sync wiring.

This module owns all business logic (sync wiring, database calls, account
management) exactly as before the visual redesign - only what renders it
changed. Every call into app.database, app.services.*, app.security.* is
unchanged from the pre-redesign version; only widget construction and
event wiring were replumbed through app.ui.components.

Threading rules kept here:
- All network work (sync, body fetch, remote flag updates) runs on QThreads.
- UI reloads triggered by sync signals are coalesced through a single-shot
  timer so heavy sync activity cannot cause reload storms or lag spikes.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app import __version__, config
from app.database import Database
from app.email import reply as reply_builder
from app.services.account_manager import AccountManager
from app.services.notifier import Notifier
from app.services.updates import ReleaseNotesStore, UpdateChecker
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
from app.ui.account_dialog import AccountDialog
from app.ui.components.email_list import EmailListView, format_time
from app.ui.components.empty_state import EmptyState
from app.ui.components.loading_state import LoadingState
from app.ui.components.preview_pane import PreviewPane
from app.ui.components.sidebar import SidebarWidget
from app.ui.components.toast import ToastHost
from app.ui.components.primitives import Button, Variant
from app.ui.components.toolbar import TopToolBar
from app.ui.components.update_button import UpdateButton
from app.ui.compose_dialog import ComposeDialog
from app.ui.console import ConsoleWidget
from app.ui.icons import make_app_icon
from app.ui.native_theme import apply_dark_titlebar
from app.ui.settings_dialog import SettingsDialog
from app.ui.shortcuts import ShortcutManager
from app.ui.shortcuts_dialog import ShortcutsDialog
from app.ui.smooth_pointer import SmoothPointer
from app.ui import motion, theme as t
from app.ui.svg_icon import simple_icon

log = logging.getLogger(__name__)

# Friendly first-launch wording for each sync phase (loading-state display)
PHASE_TEXT = {
    PH_CONNECT: "Connecting account...",
    PH_LIST: "Downloading message list...",
    PH_META: "Downloading message list...",
    PH_BODIES: "Downloading message content...",
    PH_INDEX: "Preparing mailbox...",
    PH_VERIFY: "Preparing mailbox...",
}

# Below this length a search string is treated as mid-typing: the local
# cache is still searched live, but providers are not asked (a server-side
# search per keystroke would be abusive and slow).
_REMOTE_SEARCH_MIN_CHARS = 3

# Below this window width the sidebar becomes a rail on its own. Chosen
# from what the three panes actually need: a readable message list wants
# roughly 380px and the reading pane about the same, so once the window
# is under ~1080 the drawer's fixed 248 is being taken from one of them
# rather than from slack.
_SIDEBAR_COLLAPSE_WIDTH = 1080


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

# Sync status -> the color key StatusIndicator/theme.STATUS_COLORS understands.
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

        # THE LOCATION, AND THE ONLY COPY OF IT. Two independent axes: the
        # folder (shown by the dock) and the scope - one account, or None
        # for every account (shown by the sidebar). Neither widget keeps
        # its own idea of what is current; both are told, by
        # _sync_location_widgets, after this changes. Two widgets each
        # holding their own selection is how the old drawer ended up
        # showing a folder and an account selected at once.
        self.current_view = "inbox"          # inbox | starred | sent | trash
        self.current_account_id: int | None = None
        self.current_email_id: int | None = None
        self._account_dialog: AccountDialog | None = None
        self._action_workers: list[RemoteActionWorker] = []
        self._body_workers: list[BodyFetchWorker] = []
        self._fetching_body_ids: set[int] = set()
        self._panel_account_id: int | None = None
        self._extra_limit = 0  # raised by the Load More button
        # Tracks which account ids the sidebar was last built with, so a
        # sync-progress-driven reload (fired roughly every 700ms while any
        # account is syncing) can skip rebuilding every AccountItem widget
        # when the account set itself hasn't changed - see reload_sidebar().
        self._known_account_ids: set[int] = set()
        # Which accounts actually produced a sync event since the last
        # reload - lets the debounced reload skip re-querying the email
        # list when the view on screen is scoped to an account that had
        # nothing new happen (see _schedule_reload/_do_scheduled_reload).
        self._dirty_account_ids: set[int] = set()
        self._dirty_reload_all = False
        # In-flight "fetch messages older than the cache" jobs, keyed by
        # account, so paging repeatedly can't stack duplicate fetches.
        self._older_workers: list[OlderFetchWorker] = []
        self._older_fetch_ids: set[int] = set()
        # In-flight provider-side searches, and the queries already asked
        # of the providers this session (so retyping the same search does
        # not re-hit the network).
        self._search_workers: list[RemoteSearchWorker] = []
        self._remote_searched: set[str] = set()
        # True only while the sidebar is collapsed because the WINDOW is
        # narrow, never because the user asked - see
        # _apply_responsive_layout and _on_sidebar_collapsed.
        self._auto_collapsed = False

        self.setWindowTitle("Unified")
        self.setWindowIcon(make_app_icon())
        self.resize(1280, 800)

        # APPEARANCE BEFORE ANY WIDGET IS BUILT. Half of this app paints
        # itself (row delegate, avatars, nav fill) by reading theme
        # attributes at paint time, and the other half is styled by a QSS
        # string Qt has already parsed. Binding the mode after construction
        # would leave the first group correct and the second showing the
        # previous palette until something forced a re-polish.
        self._apply_appearance_settings()
        apply_dark_titlebar(self, dark=t.is_dark())

        self._build_toolbar()
        self._build_body()
        self._build_tray()
        self.toasts = ToastHost(self)
        self._install_shortcuts()
        self.statusBar().showMessage("Ready")

        # Coalesced reload: many sync events -> at most ~1 reload per 700 ms.
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

        self.reload_sidebar()
        self._update_search_placeholder()
        self.reload_email_list()
        QTimer.singleShot(50, self._startup_integrity_check)

        # Release information. The checker offers a remembered update from
        # disk at once and asks GitHub at most hourly, on a thread, well
        # after startup; the notes are fetched only if Settings > Changelog
        # is opened. See app/services/updates.py.
        self.updates = UpdateChecker(self.settings, __version__, self)
        self.updates.update_changed.connect(self._on_update_changed)
        self.updates.start()
        self.release_notes = ReleaseNotesStore(
            config.app_data_dir() / "release_notes.json", self
        )
        # Experimental, off unless chosen in Settings > Appearance; it steps
        # aside over text, handles, drags and under reduced motion.
        self.smooth_pointer = SmoothPointer(self)
        self.smooth_pointer.set_enabled(bool(self.settings.get("smooth_pointer")))
        # A timer the window owns, not a fire-and-forget singleShot: a
        # window closed within the first 400ms must not start syncing
        # afterwards, on threads nothing will wait for.
        self._closing = False
        self._startup_sync = QTimer(self)
        self._startup_sync.setSingleShot(True)
        self._startup_sync.timeout.connect(self.start_sync)
        if self.db.get_accounts():
            self._startup_sync.start(400)

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
            self.toasts.show(
                "Database check found issues",
                "; ".join(report["problems"]), kind="error",
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
            self.toasts.show(
                "Database repaired",
                "; ".join(report["repaired"]), kind="warning",
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

    # --------------------------------------------------------------- appearance

    def _apply_appearance_settings(self) -> None:
        """Bind the saved theme and motion preference before anything is built.

        Called once from __init__ and again whenever Settings is saved.
        """
        mode = str(self.settings.get("theme_mode") or "dark")
        if mode not in t.MODES:
            mode = "dark"
        t.apply_mode(mode)
        motion.set_motion_enabled(not bool(self.settings.get("reduced_motion")))

    def set_theme_mode(self, mode: str, *, origin=None) -> None:
        """Switch palettes live, in the one order that actually works.

        THERE ARE TWO HALVES AND THEY UPDATE DIFFERENTLY. The custom
        painters (row delegate, avatars, nav fill, toasts) read
        `t.BG_SELECTED` and friends inside paintEvent, so rebinding the
        module globals and forcing a repaint is all they need. The
        stylesheet is not automatic: QSS is a string Qt parsed once, so it
        has to be rebuilt from the new tokens and re-applied. Rebind first,
        re-apply second, repaint last - any other order paints one half of
        the window in the old palette.

        The light palette has existed and been contrast-measured since the
        warm-archive pass and nothing could reach it: apply_mode() was
        called exactly once, at import, with "dark" hardcoded.
        """
        if mode not in t.MODES or mode == t.MODE:
            return
        from PySide6.QtWidgets import QApplication
        from app.ui.style import get_stylesheet, invalidate_style_cache

        def apply() -> None:
            t.apply_mode(mode)
            self.settings.set("theme_mode", mode)

            invalidate_style_cache()
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(get_stylesheet())

            apply_dark_titlebar(self, dark=t.is_dark())

            # Text colour follows the stylesheet now (theme.role), but an
            # ICON is a pixmap tinted at build time and cannot. Anything
            # holding one declares a retheme() and is found by the walker,
            # so this does not depend on a hand-maintained list of which
            # widgets those are. Top-level dialogs are walked too: Settings
            # is open when its own theme control is used.
            t.retheme_tree(self)
            for widget in (self, self.email_list.viewport(), self.console):
                widget.update()
            self.statusBar().showMessage(
                "Light theme" if mode == "light" else "Dark theme"
            )

        # The change spreads from `origin` (the theme control) when there is
        # one, and fades when there is not; see motion.reveal_theme_change.
        motion.reveal_theme_change(apply, origin=origin)

    def toggle_theme(self) -> None:
        self.set_theme_mode("light" if t.is_dark() else "dark")

    def set_compact_rows(self, compact: bool) -> None:
        """Row density, which was reachable from nothing at all.

        email_list.set_compact() and the two ROW_HEIGHT tokens have been in
        place since the row was rebuilt as three lines; no setting, no
        shortcut and no menu item ever called it.
        """
        self.settings.set("compact_rows", bool(compact))
        self.email_list.set_compact(bool(compact))
        self.statusBar().showMessage(
            "Compact rows" if compact else "Comfortable rows"
        )

    def toggle_density(self) -> None:
        self.set_compact_rows(not bool(self.settings.get("compact_rows")))

    def toggle_sidebar(self) -> None:
        # An explicit toggle ends any automatic collapse: the user has now
        # said what they want and the window must stop overruling them on
        # the next resize.
        self._auto_collapsed = False
        self.sidebar.toggle_collapsed()

    def _on_sidebar_collapsed(self, collapsed: bool) -> None:
        """Remember the drawer state, so the app opens the way it was left.

        ONLY WHEN THE USER CHOSE IT. A collapse the window performed
        because it got narrow is a response to the geometry, not a
        preference - persisting it would mean dragging the window small
        once left the drawer collapsed forever afterwards, on every
        monitor.
        """
        if self._auto_collapsed:
            return
        self.settings.set("sidebar_collapsed", bool(collapsed))

    # --------------------------------------------------------------- responsive

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        """Give the drawer back to the content when the window is small.

        This is a three-pane application, so the sidebar's fixed 248px
        comes straight out of the message list and the reading pane. At
        1000px wide that is a quarter of the window spent on four folder
        names the user already knows, while the pane they are reading is
        squeezed to 340. Below the threshold the drawer becomes a rail,
        which gives 192px back to the two surfaces the product is for.

        It reverses on the way back up, and only for collapses this made -
        see _on_sidebar_collapsed. A user who collapsed the drawer
        themselves keeps it collapsed at any width.
        """
        if self.sidebar.is_collapsed() and not self._auto_collapsed:
            return  # the user's own choice; leave it alone
        narrow = self.width() < _SIDEBAR_COLLAPSE_WIDTH
        if narrow and not self.sidebar.is_collapsed():
            self._auto_collapsed = True
            self.sidebar.set_collapsed(True)
        elif not narrow and self._auto_collapsed:
            self._auto_collapsed = False
            self.sidebar.set_collapsed(False)

    # --------------------------------------------------------------- shortcuts

    def _install_shortcuts(self) -> None:
        """Give the app a keyboard.

        app/ui/shortcuts.py has been complete, documented and imported by
        nothing since it was written: every action in this mail client
        required the mouse. The handler table is the whole wiring - the
        bindings, their guards and the help sheet all come from that
        module, so a binding cannot exist without appearing in the sheet.
        """
        self._shortcuts = ShortcutManager(self, {
            "next_message": lambda: self._step_message(1),
            "prev_message": lambda: self._step_message(-1),
            "open_message": self._open_focused_message,
            "mark_unread": self._mark_current_unread,
            "toggle_star": self._toggle_star,
            "delete_message": self._delete_current,
            "focus_search": self._focus_search,
            "escape": self._on_escape,
            "compose": self.open_compose,
            "refresh": self.start_sync,
            "toggle_theme": self.toggle_theme,
            "toggle_density": self.toggle_density,
            "toggle_sidebar": self.toggle_sidebar,
            "settings": self.open_settings,
            "show_shortcuts": self.show_shortcuts,
            "go_inbox": lambda: self._on_view_selected("inbox"),
            "go_starred": lambda: self._on_view_selected("starred"),
            "go_sent": lambda: self._on_view_selected("sent"),
            "go_trash": lambda: self._on_view_selected("trash"),
        })
        self._shortcuts.install()

    def _step_message(self, delta: int) -> None:
        """Move the selection by one real message.

        Skips the synthetic date-group headers, which are rows in the same
        flat model but are not selectable - stepping onto one would look
        like the keyboard had stopped working.
        """
        rows = self.email_list._model._rows
        if not rows:
            return
        selectable = [i for i, row in enumerate(rows) if not row.get("is_header")]
        if not selectable:
            return
        current = self.email_list.currentIndex().row()
        if current in selectable:
            position = selectable.index(current)
            position = max(0, min(len(selectable) - 1, position + delta))
        else:
            position = 0 if delta > 0 else len(selectable) - 1
        index = self.email_list._model.index(selectable[position], 0)
        self.email_list.setCurrentIndex(index)
        self.email_list.scrollTo(index)
        self.email_list.setFocus()

    def _open_focused_message(self) -> None:
        email_id = self.email_list.selected_email_id()
        if email_id is not None:
            self._on_email_selected(email_id)
            self.preview.setFocus()

    def _focus_search(self) -> None:
        self.toolbar.search_edit.setFocus()
        self.toolbar.search_edit.selectAll()

    def _on_escape(self) -> None:
        """Escape means "back out one step", and which step depends on where
        you are: clear a search you are in, otherwise return to the list."""
        if self.toolbar.search_edit.hasFocus() and self.toolbar.search_text():
            self.toolbar.search_edit.clear()
            return
        self.email_list.setFocus()

    def _mark_current_unread(self) -> None:
        email_id = self.email_list.selected_email_id() or self.current_email_id
        if email_id is None:
            return
        msg = self.db.get_email(email_id)
        if not msg or not msg["is_read"]:
            return
        self.db.set_read(email_id, False)
        self._remote_action(msg, "read", False)
        self.reload_email_list()
        self.reload_sidebar()
        self.statusBar().showMessage("Marked unread")

    def show_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()

    # ------------------------------------------------------------------ toolbar

    def _build_toolbar(self) -> None:
        # The menu-widget slot, not addToolBar: the band spans the whole
        # window above everything else, and a QMainWindow toolbar would
        # bring a right-click menu that can hide it.
        self.toolbar = TopToolBar()
        self.setMenuWidget(self.toolbar)
        self.toolbar.compose_clicked.connect(self.open_compose)
        self.toolbar.refresh_clicked.connect(self.start_sync)
        self.toolbar.console_toggled.connect(self._toggle_console)
        self.toolbar.search_changed.connect(self._on_search_changed)
        self.dock = self.toolbar.dock
        self.dock.folder_requested.connect(self._on_view_selected)
        self.dock.action_requested.connect(self._on_dock_action)
        # Hidden until a newer release is found; hidden widgets take no
        # room in the band, so there is no gap waiting for it.
        self.update_btn = UpdateButton()
        self.toolbar.add_trailing(self.update_btn)

    def _on_update_changed(self, release) -> None:
        self.update_btn.set_release(release)
        self.toolbar.relayout()

    def _on_dock_action(self, key: str) -> None:
        if key == "add_account":
            self.open_add_account()
        elif key == "settings":
            self.open_settings()

    # --------------------------------------------------------------------- body

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.sidebar = SidebarWidget()
        self.sidebar.scope_selected.connect(self._on_scope_selected)
        self.sidebar.collapsed_changed.connect(self._on_sidebar_collapsed)
        # Restored without animating: the window has not been shown yet, so
        # there is nothing for a 280ms width tween to narrate.
        if bool(self.settings.get("sidebar_collapsed")):
            self.sidebar.set_collapsed(True, animate=False)

        self.email_list = EmailListView()
        self.email_list.email_selected.connect(self._on_email_selected)
        self.email_list.context_menu_requested.connect(self._on_email_context_menu)
        # THE HOVER QUICK ACTIONS WERE PAINTED, HIT-TESTED AND UNCONNECTED.
        # EmailListView has emitted these two since the row was rebuilt;
        # nothing listened, so the star and trash glyphs that appear on a
        # hovered row did precisely nothing when clicked. A control that
        # draws itself, lights up under the pointer and then ignores the
        # click is worse than one that was never drawn.
        self.email_list.star_toggled.connect(self._star_row)
        self.email_list.delete_requested.connect(self._delete_row)
        self.email_list.set_compact(bool(self.settings.get("compact_rows")))

        # List page: the list plus a Load More button that appears whenever
        # the display limit hides messages (so nothing ever looks missing).
        list_page = QWidget()
        lp = QVBoxLayout(list_page)
        lp.setContentsMargins(0, 0, 0, 0)
        lp.setSpacing(0)
        # SECONDARY, AND CENTRED UNDER THE LIST IT EXTENDS. It was a bare
        # QPushButton stretched across the full width of the pane, which
        # made paging - the least important action on the screen - the
        # widest control in the window. It is also the shared vocabulary
        # now rather than whatever a default QPushButton happens to look
        # like.
        self.load_more_btn = Button("Load more", Variant.SECONDARY)
        self.load_more_btn.setVisible(False)
        self.load_more_btn.clicked.connect(self._load_more)
        load_more_row = QWidget()
        lm = QHBoxLayout(load_more_row)
        lm.setContentsMargins(0, t.SPACE_SM, 0, t.SPACE_SM)
        lm.addStretch(1)
        lm.addWidget(self.load_more_btn)
        lm.addStretch(1)
        self._load_more_row = load_more_row
        load_more_row.setVisible(False)
        lp.addWidget(self.email_list, stretch=1)
        lp.addWidget(load_more_row)

        self.loading_state = LoadingState()
        self.empty_state = EmptyState()

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(list_page)
        self.center_stack.addWidget(self.loading_state)
        self.center_stack.addWidget(self.empty_state)
        splitter.addWidget(self.center_stack)

        self.preview = PreviewPane()
        self.preview.star_clicked.connect(self._toggle_star)
        self.preview.delete_clicked.connect(self._delete_current)
        self.preview.mark_unread_clicked.connect(self._mark_current_unread)
        self.preview.reply_clicked.connect(lambda: self._compose_from("reply"))
        self.preview.reply_all_clicked.connect(lambda: self._compose_from("reply_all"))
        self.preview.forward_clicked.connect(lambda: self._compose_from("forward"))
        splitter.addWidget(self.preview)

        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([660, 380])
        self._pane_splitter = splitter

        # THE SIDEBAR IS BESIDE THE SPLITTER, NOT IN IT. It has a fixed
        # width - it is not user-resizable - so a splitter handle next to it
        # did nothing, and worse: when the drawer collapsed to its 56px rail
        # the splitter kept the old 248px section and left 192px of dead
        # floor between the rail and the list. The width collapsing was
        # supposed to give back to the two panes never reached them. A box
        # layout re-reads a fixed width on every change, including every
        # frame of the collapse animation.
        body = QWidget()
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.addWidget(self.sidebar)
        body_row.addWidget(splitter, 1)

        # -- Console under the main area (collapsible, hidden by default)
        self.console = ConsoleWidget()
        self.console.setVisible(False)

        self._vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self._vertical_splitter.addWidget(body)
        self._vertical_splitter.addWidget(self.console)
        self._vertical_splitter.setStretchFactor(0, 4)
        self._vertical_splitter.setStretchFactor(1, 1)
        # The console starts hidden, so it must start at 0 height too - a
        # QSplitter reserves proportional space for a child regardless of
        # that child's own visibility, so leaving this at a nonzero size
        # (e.g. 140) would silently steal that much height from the sidebar/
        # list/preview above it even while the console is never shown.
        self._vertical_splitter.setSizes([1, 0])
        self.setCentralWidget(self._vertical_splitter)

    def _toggle_console(self, visible: bool) -> None:
        self.console.setVisible(visible)
        total = sum(self._vertical_splitter.sizes()) or self.height()
        if visible:
            self._vertical_splitter.setSizes([max(1, total - 260), 260])
        else:
            self._vertical_splitter.setSizes([total, 0])

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
        """Refresh the sidebar's counts/status without rebuilding the
        account list widgets unless the account set itself changed.

        This is called on every debounced sync-progress reload (roughly
        every 700ms while any account is actively syncing), so rebuilding
        every AccountItem from scratch each time - the previous behavior -
        meant the entire sidebar tore down and recreated its widgets in a
        loop for as long as sync ran. That's real, wasted UI-thread work
        during exactly the window the app most needs to stay responsive,
        and it reads to the user as "the sidebar keeps reloading/
        re-downloading" even though no new sync was actually starting.
        """
        counts = self.db.unread_counts()
        accounts = self.db.get_accounts()
        account_ids = {a["id"] for a in accounts}
        if account_ids != self._known_account_ids:
            self.sidebar.set_accounts(accounts, counts["per_account"])
            self._known_account_ids = account_ids
            if (self.current_account_id is not None
                    and self.current_account_id not in account_ids):
                # The account on screen was removed: fall back to everyone.
                self.current_account_id = None
            self._update_search_placeholder()
        else:
            self.sidebar.update_unread_counts(counts["per_account"])
        self._unread_counts = counts
        self._sync_location_widgets(animate=False)
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
            return "waiting", "Waiting"
        if status == ST_ERROR:
            result = state.get("result", {})
            reason = result.get("error", "unknown error")
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
                f"Complete - {result.get('local_total', 0):,}/"
                f"{result.get('server_total', 0):,} verified"
            )
        if account["initial_sync_completed"]:
            return "done", "Synced"
        return "idle", ""

    def _update_account_status_display(self, account_id: int) -> None:
        account = self.db.get_account(account_id)
        if account is None:
            return
        status_key, text = self._account_status(account)
        self.sidebar.update_account_status(account_id, status_key, text)

    def _on_view_selected(self, view: str) -> None:
        """A folder from the dock (or Ctrl+1..4). The scope is kept: Sent
        while looking at one account means that account's Sent."""
        self._navigate(view=view)

    def _on_account_selected(self, account_id: int) -> None:
        """A scope from the sidebar. The folder is kept."""
        self._navigate(account_id=account_id)

    def _on_scope_selected(self, scope) -> None:
        self._navigate(account_id=scope)

    _KEEP = object()

    def _navigate(self, *, view: str | None = None, account_id=_KEEP) -> None:
        """Change where the user is. The one entry point for it.

        Everything that shows the location - the dock, the sidebar, the
        search placeholder, the list - is refreshed from the state set
        here, so no widget can disagree with another about it.
        """
        moved = False
        if view is not None and view != self.current_view:
            self.current_view = view
            moved = True
        if account_id is not self._KEEP and account_id != self.current_account_id:
            self.current_account_id = account_id
            moved = True
        self._extra_limit = 0
        self._sync_location_widgets()
        self._update_search_placeholder()
        self.reload_email_list()
        if moved:
            self._let_go_of_a_message_left_behind()
            self._reveal_list()

    def _let_go_of_a_message_left_behind(self) -> None:
        """A message open in Inbox is not in Trash.

        The reading pane used to keep showing it after the user moved to a
        folder or account that does not contain it - a page from somewhere
        else, with Reply and Delete still acting on it. And coming back
        later re-selected its row while the pane had meanwhile been
        blanked by an empty folder: a highlighted row with nothing open.
        Moving somewhere the message is not lets go of it.
        """
        if self.current_email_id is None:
            return
        if self.email_list._model.index_of(self.current_email_id).isValid():
            return
        self.current_email_id = None
        if self.email_list.row_count():
            self.preview.reset()
        else:
            self.preview.show_nothing()

    def _sync_location_widgets(self, *, animate: bool = True) -> None:
        """Tell the dock and the sidebar where the user is. Never the other
        way round - see the note on current_view in __init__."""
        self.dock.set_current_folder(self.current_view, animate=animate)
        self.sidebar.set_current_scope(self.current_account_id)
        counts = getattr(self, "_unread_counts", None) or {"total": 0, "per_account": {}}
        # The inbox badge counts the inbox the Inbox icon would open: every
        # account's, or only the one in scope.
        if self.current_account_id is None:
            self.dock.set_unread(counts["total"])
        else:
            self.dock.set_unread(counts["per_account"].get(self.current_account_id, 0))

    def _reveal_list(self) -> None:
        """Let the list arrive when the user changed WHERE THEY ARE.

        Adapted from Magic UI's BlurFade (offset + fade; the blur is
        dropped - see motion.reveal). The point is that switching folder
        or account is a change of context, and content that simply
        replaces itself in place gives the eye nothing to tell it the
        ground moved.

        DELIBERATELY NOT CALLED FROM reload_email_list(). That runs on
        every debounced sync tick - roughly once a second while any
        account is syncing - and a list that re-revealed itself that
        often would be unreadable. It is bound to the two things the user
        actually did.
        """
        motion.reveal(self.email_list)

    _FOLDER_NAMES = {"inbox": "Inbox", "starred": "Starred", "sent": "Sent",
                     "trash": "Trash"}

    def _update_search_placeholder(self) -> None:
        """Search always scopes to whatever is currently shown, so the field
        says what that is: the folder, and whose."""
        folder = self._FOLDER_NAMES.get(self.current_view, "mail").lower()
        if not self.db.get_accounts():
            text = "Search"
        elif self.current_account_id is None:
            text = f"Search {folder} in all accounts"
        else:
            account = self.db.get_account(self.current_account_id)
            text = f"Search {folder} in {account['email']}" if account \
                else f"Search {folder}"
        self.toolbar.set_search_placeholder(text)

    # --------------------------------------------------------------- email list

    def _schedule_reload(self, account_id: int | None = None) -> None:
        """Coalesce reloads into at most one per 700ms. account_id, when
        given, marks only that account as having new data - a debounced
        tick then skips re-querying the email list if the view on screen
        is scoped to a *different* single account, since nothing in it
        could have changed. Omitting account_id (user actions: star/read/
        delete, or the end-of-round all_finished signal) always refreshes,
        matching the previous unconditional behavior for those paths.
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
        # The Unified Mailbox view (current_account_id is None) can be
        # affected by any account, so it always refreshes; a view scoped
        # to one account only needs to when that account was the one with
        # new data.
        if reload_all or self.current_account_id is None or self.current_account_id in dirty_ids:
            self.reload_email_list()

    def _on_search_changed(self, _text: str) -> None:
        self._extra_limit = 0
        self._search_timer.start()

    def _run_search(self) -> None:
        """Show local cache hits immediately, then - only if the query
        looks deliberate - ask each provider to search its own server for
        anything the cache never held. The visible list is never blocked
        on the network; remote hits land later and refresh it."""
        self.reload_email_list()
        query = self.toolbar.search_text()
        # Very short fragments are almost always mid-typing, and a remote
        # search per keystroke would be abusive to the provider.
        if len(query) < _REMOTE_SEARCH_MIN_CHARS:
            return
        if query in self._remote_searched:
            return  # already asked the providers for exactly this
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
        self.statusBar().showMessage(f'Searching the server for "{query}"...')

    def _on_remote_search_done(self, query: str, added: int) -> None:
        # Ignore results for a query the user has already moved on from.
        if self.toolbar.search_text() != query:
            return
        if added:
            self.reload_email_list()

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
            self.statusBar().showMessage("Loading older messages...")

    def _on_older_loaded(self, account_id: int, added: int) -> None:
        if added:
            self.reload_email_list()
        elif not self._older_fetch_ids:
            self.statusBar().showMessage("No older messages on the server")

    def _on_older_failed(self, account_id: int, reason: str) -> None:
        self.statusBar().showMessage(f"Could not load older messages: {reason}")
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
        )
        total = self.db.count_emails(
            folder=folder,
            account_id=self.current_account_id,
            starred_only=starred,
            search=search,
        )

        self.email_list.set_rows(emails, keep_selected_id=self.current_email_id)

        shown = len(emails)
        if total > shown:
            self.statusBar().showMessage(
                f"Showing newest {shown:,} of {total:,} emails"
                " - use Load more or search to reach older mail"
            )
            # The count belongs in the status bar, which is already saying
            # it; a button's label is what it DOES. "Load more (showing
            # 100 of 2,431 emails)" is a sentence pretending to be a
            # control, and it changed width on every reload.
            self.load_more_btn.setText("Load more")
            self.load_more_btn.setToolTip(
                f"Showing the newest {shown:,} of {total:,} cached messages"
            )
            self.load_more_btn.setVisible(True)
            self._load_more_row.setVisible(True)
        else:
            if not self._known_account_ids:
                self.statusBar().showMessage("No accounts connected")
            else:
                self.statusBar().showMessage(
                    f"{total:,} message{'s' if total != 1 else ''}"
                )
            self.load_more_btn.setVisible(False)
            self._load_more_row.setVisible(False)
        self._refresh_center_page(shown)

    def _refresh_center_page(self, email_count: int) -> None:
        """Three alternatives to the live list, tried in order: a pending
        account's sync progress, a friendly empty state (no accounts, an
        empty folder, no search results), or - once metadata lands - the
        list itself, so the app stays usable during sync.
        """
        accounts = self.db.get_accounts()
        # Compose is an offer, and it is only true once there is somewhere to
        # send from. See TopToolBar.set_compose_enabled. Search and sync
        # follow the same rule.
        self.toolbar.set_compose_enabled(bool(accounts))
        self.toolbar.set_mailbox_available(bool(accounts))
        self._set_reading_pane_present(bool(accounts))
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
            and not self.toolbar.search_text()
        ):
            account = next(
                (a for a in accounts if self.sync.is_account_pending(a["id"])),
                None,
            )
        if account is not None:
            self._panel_account_id = account["id"]
            self._update_loading_state(account)
            self.center_stack.setCurrentIndex(1)
            return
        self._panel_account_id = None

        if email_count == 0:
            self._show_empty_state(has_accounts=bool(accounts))
            self.center_stack.setCurrentIndex(2)
            return
        self.center_stack.setCurrentIndex(0)
        if not self.preview.is_showing_message():
            # Back from an empty folder: the pane was blank because there
            # was nothing to pick. Now there is, so it says so.
            self.preview.reset()

    def _set_reading_pane_present(self, present: bool) -> None:
        """No accounts, no reading pane.

        THE EMPTY STATE WAS THE POPULATED LAYOUT WITH THE DATA TAKEN OUT.
        With nothing connected the window still reserved a reading pane -
        on a 1440px screen, a 440px blank column with a divider down it,
        beside a list pane whose only content was the offer to add an
        account. Nothing will ever be read in it until an account exists,
        so it goes, and the offer is centred in the space it was holding.
        The splitter remembers the pane's width, so it comes back exactly
        where it was.
        """
        if self.preview.isHidden() == (not present):
            return
        self.preview.setVisible(present)

    def _show_empty_state(self, *, has_accounts: bool) -> None:
        search = self.toolbar.search_text()
        if not has_accounts:
            self.empty_state.set_state(
                icon="add_circle", title="No accounts yet",
                detail="Connect a Gmail or IMAP account. Unified keeps an "
                       "encrypted copy of your mail on this machine, so it "
                       "stays readable offline.",
                action_text="Add account", on_action=self.open_add_account,
            )
            # ONE OFFER PER SCREEN. The reading pane is hidden with no
            # accounts (see _set_reading_pane_present); blanking it too
            # means it comes back empty rather than with a stale message.
            self.preview.show_nothing()
            return
        self.preview.show_nothing()
        if search:
            self.empty_state.set_state(
                icon="search", title="No results",
                detail=f'Nothing in the local cache matches "{search}".',
            )
        elif self.current_view == "starred":
            self.empty_state.set_state(
                icon="star_outline", title="No starred messages",
                detail="Starred messages collect here.",
            )
        elif self.current_view == "sent":
            self.empty_state.set_state(
                icon="sent", title="No sent messages yet",
                detail="Messages you send collect here.",
            )
        elif self.current_view == "trash":
            self.empty_state.set_state(
                icon="trash", title="Trash is empty",
                detail="Deleted messages collect here.",
            )
        else:
            self.empty_state.set_state(
                icon="inbox", title="Inbox is empty",
                detail="New mail arrives here as it syncs.",
            )

    def _update_loading_state(self, account: dict) -> None:
        state = self.sync.status(account["id"])
        if state["status"] == ST_SYNCING:
            phase = state.get("phase", PH_CONNECT)
            done, total = state.get("done", 0), state.get("total", 0)
            friendly = PHASE_TEXT.get(phase, phase + "...")
            if account["provider"] == "gmail" and phase == PH_CONNECT:
                friendly = "Connecting Gmail..."
            detail = f"{phase}  {done:,} / {total:,}" if total else (
                f"{phase}: {done:,} found" if done else phase
            )
            self.loading_state.set_state(
                account["email"], friendly, detail, done, total
            )
        elif state["status"] == ST_WAITING:
            self.loading_state.set_state(
                account["email"], "Waiting to sync...",
                "Another account is currently syncing",
            )
        else:
            self.loading_state.set_state(
                account["email"], "Loading mailbox...", "Preparing mailbox...",
            )

    # ------------------------------------------------------------------ preview

    def _on_email_selected(self, email_id: int) -> None:
        msg = self.db.get_email(email_id)
        if not msg:
            # Deleted under us (pruned by sync) - explain, never blank.
            self.preview.show_placeholder(
                "Message unavailable",
                "This message is no longer available.\n\n"
                "It may have been deleted or moved on the server.",
            )
            return
        self.current_email_id = email_id

        self.preview.show_message(
            subject=msg["subject"],
            sender_name=msg["sender_name"],
            sender_email=msg["sender_email"],
            recipients=msg["recipients"] or "",
            account_email=msg["account_email"],
            time_text=format_time(msg["date_ts"]),
            has_attachments=bool(msg["has_attachments"]),
            is_starred=bool(msg["is_starred"]),
        )
        self.preview.set_attachments(_decode_attachments(msg))

        if msg["body_fetched"]:
            self._render_body(msg)
        else:
            self.preview.body.set_email_text(
                "Loading email...\n\nDownloading message content..."
            )
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
        self.preview.body.set_email_text("Rendering preview...")
        self._render_body(msg)
        if msg["has_attachments"]:
            # Attachment flag becomes known only after the full fetch.
            self.preview.set_attachment_visible(True)

    def _on_body_failed(self, email_id: int, reason: str) -> None:
        if email_id != self.current_email_id:
            return
        self.preview.body.set_email_text(
            "Could not load this message.\n\n"
            f"{reason}\n\nSelect the message again to retry."
        )

    # ------------------------------------------------------------------ actions

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
        self.statusBar().showMessage(f"Server update failed: {err}")
        self.toasts.show("Server update failed", err, kind="error")

    def _toggle_star(self) -> None:
        """Star the message being READ (reading pane button, `s` shortcut)."""
        if self.current_email_id is None:
            # No message open, but the list may still have one focused -
            # `s` should act on what the user is looking at.
            focused = self.email_list.selected_email_id()
            if focused is None:
                return
            self._star_row(focused)
            return
        msg = self.db.get_email(self.current_email_id)
        if not msg:
            return
        new_state = not msg["is_starred"]
        self.db.set_starred(self.current_email_id, new_state)
        self._remote_action(msg, "star", new_state)
        self.preview.set_starred(new_state)
        self._schedule_reload()

    def _star_row(self, email_id: int) -> None:
        """Star a row from the LIST, without selecting it.

        Deliberately distinct from _toggle_star: starring the fourth
        message in the list must not throw away the message currently open
        in the reading pane. The list's own mousePressEvent already
        declines to change the selection for a quick-action click; this is
        the other half of that contract.
        """
        msg = self.db.get_email(email_id)
        if not msg:
            return
        new_state = not msg["is_starred"]
        self.db.set_starred(email_id, new_state)
        self._remote_action(msg, "star", new_state)
        if email_id == self.current_email_id:
            self.preview.set_starred(new_state)
        self.reload_email_list()
        self.statusBar().showMessage("Starred" if new_state else "Unstarred")

    def _delete_row(self, email_id: int) -> None:
        """Delete a row from the list, selection untouched unless it WAS
        the open message - in which case the reading pane has to let go of
        a message that no longer exists."""
        msg = self.db.get_email(email_id)
        if not msg:
            return
        if msg["folder"] == "trash":
            self.statusBar().showMessage("Already in Trash")
            return
        self.db.move_to_trash(email_id)
        self._remote_action(msg, "trash")
        if email_id == self.current_email_id:
            self.current_email_id = None
            self.preview.reset()
        self.reload_email_list()
        self.reload_sidebar()
        self.statusBar().showMessage("Moved to Trash")

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
        self.preview.reset()
        self.reload_email_list()
        self.reload_sidebar()

    def _on_email_context_menu(self, email_id: int, global_pos) -> None:
        msg = self.db.get_email(email_id)
        if not msg:
            return
        menu = QMenu(self)
        mark = menu.addAction(
            "Mark as unread" if msg["is_read"] else "Mark as read"
        )
        star_icon_name = "star_filled" if msg["is_starred"] else "star_outline"
        star = menu.addAction(
            simple_icon(star_icon_name, 15, t.ICON_SECONDARY),
            "Unstar" if msg["is_starred"] else "Star",
        )
        delete = menu.addAction(
            simple_icon("trash", 15, t.ICON_SECONDARY), "Delete"
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
        if self._closing:
            return
        accounts = self.db.get_accounts()
        if not accounts:
            self.statusBar().showMessage("Add an account to start syncing")
            return
        self.sync.request_sync([a["id"] for a in accounts])

    def _on_account_progress(
        self, account_id: int, phase: str, done: int, total: int
    ) -> None:
        self._update_account_status_display(account_id)
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
            self.statusBar().showMessage(f"Sync error - {email}: {result['error']}")
            self.toasts.show(f"Sync error - {email}", result["error"], kind="error")
        elif result.get("cancelled"):
            pass
        elif result.get("failed"):
            detail = (
                f"{result['local_total']:,}/{result['server_total']:,} downloaded, "
                f"{result['failed']:,} failed. Press Refresh to retry."
            )
            self.statusBar().showMessage(f"Sync completed with issues - {email}: {detail}")
            self.toasts.show(f"Sync completed with issues - {email}", detail, kind="warning")
        elif result.get("was_initial"):
            self.statusBar().showMessage(
                f"Mailbox ready - {email}: "
                f"{result['local_total']:,} messages verified in local cache"
            )
        self._schedule_reload(account_id)

    def _on_all_finished(self, notify_count: int) -> None:
        self._schedule_reload()
        if notify_count:
            plural = "s" if notify_count != 1 else ""
            message = f"{notify_count} new message{plural}"
            self.statusBar().showMessage(f"Sync complete - {message}")
            if self.isActiveWindow():
                # The window already has focus, so the tray balloon would go
                # unseen - an in-app toast is the visible equivalent.
                self.toasts.show("Sync complete", message, kind="success")
        self.notifier.notify_new_mail(notify_count)

    # ------------------------------------------------------------------ dialogs

    def open_compose(self) -> None:
        accounts = self.db.get_accounts()
        if not accounts:
            self.statusBar().showMessage("Add an account before writing a message")
            return
        dialog = ComposeDialog(accounts, self)
        dialog.sent.connect(self._on_message_sent)
        dialog.exec()

    def _compose_from(self, mode: str) -> None:
        """Open a reply, reply-all or forward for the message being read.

        The account the message ARRIVED AT is what it is sent from, not
        whichever account happens to be first in the list: replying to
        work mail from a personal address is the kind of mistake an
        interface should make impossible rather than merely unlikely.
        """
        if self.current_email_id is None:
            return
        msg = self.db.get_email(self.current_email_id)
        if not msg:
            self.statusBar().showMessage("That message is no longer available")
            return
        accounts = self.db.get_accounts()
        if not accounts:
            return

        account = next(
            (a for a in accounts if a["id"] == msg["account_id"]), accounts[0]
        )
        fields = reply_builder.prepare(msg, mode, account["email"])
        dialog = ComposeDialog(
            accounts, self, mode=mode,
            to=fields["to"], cc=fields["cc"],
            subject=fields["subject"], body=fields["body"],
            from_account=account,
        )
        dialog.sent.connect(self._on_message_sent)
        dialog.exec()

    def _on_message_sent(self) -> None:
        self.statusBar().showMessage("Message sent")
        self.toasts.show("Message sent", "", kind="success")

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
            # Jump to the new account's inbox; it queues immediately even if
            # other accounts are mid-sync (shows Waiting/progress, never
            # empty). The sidebar is rebuilt FIRST so the new row exists to
            # be selected.
            self.reload_sidebar()
            self._navigate(view="inbox", account_id=account["id"])
            self.sync.request_sync([account["id"]])

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.manager, self,
                                release_notes=self.release_notes)
        # The theme applies the moment it is chosen - it is the one setting
        # whose effect has to be seen to be judged - and Cancel puts it back.
        dialog.theme_requested.connect(
            lambda mode, origin: self.set_theme_mode(mode, origin=origin)
        )
        if dialog.exec():
            self._apply_sync_interval()
            # Appearance can have moved under us: the dialog writes
            # theme_mode / compact_rows / reduced_motion straight to
            # Settings, so the window applies whatever is now stored rather
            # than assuming nothing visual changed.
            motion.set_motion_enabled(not bool(self.settings.get("reduced_motion")))
            self.set_theme_mode(str(self.settings.get("theme_mode") or "dark"))
            self.smooth_pointer.set_enabled(bool(self.settings.get("smooth_pointer")))
            self.email_list.set_compact(bool(self.settings.get("compact_rows")))
            if dialog.accounts_changed:
                remaining = {a["id"] for a in self.db.get_accounts()}
                for aid in self.sync.known_account_ids():
                    if aid not in remaining:
                        self.sync.forget_account(aid)
                self.reload_sidebar()
                self.reload_email_list()

    # ------------------------------------------------------------------- close

    def closeEvent(self, event) -> None:
        self._closing = True
        self._startup_sync.stop()
        self._sync_timer.stop()
        self._reload_timer.stop()
        self.updates.shutdown()
        self.release_notes.shutdown()
        self.smooth_pointer.shutdown()
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

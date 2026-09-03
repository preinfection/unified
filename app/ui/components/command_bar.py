"""The top command bar.

Replaces the old `QToolBar`, which came with a movable handle, a
separator style Unified never wanted, and platform toolbar chrome that
had to be styled back out. This is a plain widget with a layout, so its
height, alignment and spacing are exactly the tokens and nothing else.

Contents, left to right, in the order a first-time user needs them:

    [ mark  Unified ]  [ Compose ]  [refresh]    [ search ]    [theme][more]

* The app mark and wordmark answer "what am I looking at" - the previous
  design put the product name in the sidebar, where it competed with
  navigation and disappeared entirely once the sidebar collapsed.
* Compose is the one filled button in the entire window. Being the only
  one is what makes it read as primary; a toolbar of five accent buttons
  has no primary action at all.
* Everything secondary is an icon with a tooltip *and* an accessible
  name, in one consistent size - not a mix of icon-plus-label and
  icon-only buttons.
* The overflow menu carries the things that belong to the application
  rather than to the mailbox (settings, accounts, appearance, about),
  which keeps them one predictable click away instead of scattered.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QWidget

from app import APP_NAME
from app.ui import theme as t
from app.ui.components.buttons import IconButton, PrimaryButton
from app.ui.components.search_field import SearchField
from app.ui.icons import make_mark
from app.ui.svg_icon import themed

_SEARCH_WIDTH = 420
_SEARCH_WIDTH_MIN = 200


class CommandBar(QWidget):
    compose_clicked = Signal()
    refresh_clicked = Signal()
    console_toggled = Signal(bool)
    search_changed = Signal(str)
    search_escaped = Signal()
    settings_requested = Signal()
    add_account_requested = Signal()
    theme_requested = Signal(str)     # "system" | "light" | "dark"
    density_requested = Signal(str)
    sidebar_toggled = Signal()
    about_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("commandBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(t.COMMAND_BAR_HEIGHT)

        row = QHBoxLayout(self)
        row.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        row.setSpacing(t.SPACE_MD)

        # -- identity
        self.sidebar_button = IconButton(
            "panel_left", "Show or hide the sidebar (Ctrl+B)", size="sm"
        )
        self.sidebar_button.clicked.connect(self.sidebar_toggled.emit)
        row.addWidget(self.sidebar_button)

        self.mark = QLabel()
        self.mark.setFixedSize(t.ICON_LG, t.ICON_LG)
        self.mark.setAccessibleName(APP_NAME)
        row.addWidget(self.mark, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.wordmark = QLabel(APP_NAME)
        self.wordmark.setFont(t.make_font("subheading"))
        row.addWidget(self.wordmark, alignment=Qt.AlignmentFlag.AlignVCenter)

        row.addSpacing(t.SPACE_MD)

        # -- primary + mailbox actions
        self.compose_button = PrimaryButton(
            "Compose", icon="compose", size="md",
            tooltip="Write a new message (Ctrl+N)",
        )
        self.compose_button.clicked.connect(self.compose_clicked.emit)
        row.addWidget(self.compose_button)

        self.refresh_button = IconButton("refresh", "Sync all accounts (F5)")
        self.refresh_button.clicked.connect(self.refresh_clicked.emit)
        row.addWidget(self.refresh_button)

        row.addStretch(1)

        # -- search
        self.search_edit = SearchField()
        self.search_edit.setMinimumWidth(_SEARCH_WIDTH_MIN)
        self.search_edit.setMaximumWidth(_SEARCH_WIDTH)
        self.search_edit.textChanged.connect(self.search_changed.emit)
        self.search_edit.escaped.connect(self.search_escaped.emit)
        row.addWidget(self.search_edit, stretch=3)

        row.addStretch(1)

        # -- app-level actions
        self.theme_button = IconButton("moon", "Appearance", size="md")
        self.theme_button.clicked.connect(self._show_theme_menu)
        row.addWidget(self.theme_button)

        self.console_button = IconButton(
            "console", "Developer console (Ctrl+`)", checkable=True
        )
        self.console_button.toggled.connect(self.console_toggled.emit)
        row.addWidget(self.console_button)

        self.more_button = IconButton("more_horizontal", "More actions")
        self.more_button.clicked.connect(self._show_more_menu)
        row.addWidget(self.more_button)

        self.refresh_mark()
        self.refresh_theme_icon()

    def refresh_mark(self) -> None:
        self.mark.setPixmap(make_mark(t.ICON_LG, t.TEXT_PRIMARY))

    # -------------------------------------------------------------- search

    def set_search_placeholder(self, text: str) -> None:
        self.search_edit.setPlaceholderText(text)

    def search_text(self) -> str:
        return self.search_edit.text().strip()

    def focus_search(self) -> None:
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_edit.selectAll()

    # --------------------------------------------------------------- menus

    def refresh_theme_icon(self) -> None:
        """The button shows the mode you are in, not the one you would
        switch to - an icon that means "click for the opposite" is a
        riddle, and this one also has to represent 'follow the system'."""
        mode = t.theme_manager.mode
        icon = {"system": "monitor", "light": "sun", "dark": "moon"}[mode]
        self.theme_button.set_icon(icon)
        self.theme_button.setToolTip(f"Appearance: {mode.capitalize()}")

    def refresh_icons(self) -> None:
        for button in (self.sidebar_button, self.refresh_button, self.console_button,
                       self.more_button, self.compose_button):
            button.refresh_icon()
        self.search_edit.refresh_icon()
        self.refresh_mark()
        self.refresh_theme_icon()

    def _show_theme_menu(self) -> None:
        menu = QMenu(self)
        current = t.theme_manager.mode
        for mode, label, icon in (
            ("system", "Match Windows", "monitor"),
            ("light", "Light", "sun"),
            ("dark", "Dark", "moon"),
        ):
            action = menu.addAction(themed(icon, t.ICON_SM, "default"), label)
            action.setCheckable(True)
            action.setChecked(mode == current)
            action.triggered.connect(lambda _=False, m=mode: self.theme_requested.emit(m))
        menu.exec(self.theme_button.mapToGlobal(
            self.theme_button.rect().bottomLeft()
        ))

    def _show_more_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(
            themed("add_circle", t.ICON_SM, "default"), "Add account...",
            self.add_account_requested.emit,
        )
        menu.addAction(
            themed("settings", t.ICON_SM, "default"), "Settings...",
            self.settings_requested.emit,
        )
        menu.addSeparator()

        density_menu = menu.addMenu("List density")
        density_menu.setIcon(themed("density", t.ICON_SM, "default"))
        current = t.theme_manager.density
        for value in t.DENSITY_ORDER:
            action = density_menu.addAction(value.capitalize())
            action.setCheckable(True)
            action.setChecked(value == current)
            action.triggered.connect(
                lambda _=False, v=value: self.density_requested.emit(v)
            )

        menu.addSeparator()
        menu.addAction(
            themed("info", t.ICON_SM, "default"), f"About {APP_NAME}",
            self.about_requested.emit,
        )
        menu.exec(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))

    # ---------------------------------------------------------- responsive

    def set_compact(self, compact: bool) -> None:
        """Below the narrow breakpoint the wordmark and the Compose label
        give up their space to search; the actions themselves all stay."""
        self.wordmark.setVisible(not compact)
        self.compose_button.setText("" if compact else "Compose")
        self.compose_button.setProperty("shape", "icon" if compact else None)
        t.repolish(self.compose_button)
        self.compose_button.setIconSize(QSize(t.ICON_MD, t.ICON_MD))


# The pre-redesign name, kept so `window.toolbar` keeps meaning the same
# thing to anything that reaches for it.
TopToolBar = CommandBar

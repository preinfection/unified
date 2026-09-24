"""Settings: appearance, sync, the Google OAuth client file, and accounts,
presented as a rail-navigated set of pages rather than one long scrolling
column - a narrow icon+label strip on the left drives a QStackedWidget on
the right, which is what keeps a settings surface from turning into an
endless scroll once it has more than a couple of groups.

=========================================================================
WHAT CHANGED, AND WHY

  EVERY ROW EXPLAINS ITSELF. A settings row used to be a label and a
  control, which works for "Sync every" and fails for "Messages shown per
  view" - a phrase that names a number without saying what the number
  does, or why 100 rather than 5,000. The description line underneath is
  where the product says the true thing plainly, which is the fourth
  design principle in PRODUCT.md and the one a settings screen is asked to
  keep most often.

  APPEARANCE EXISTS. The light palette, the compact row height and the
  reduced-motion switch were all implemented and contrast-checked, and
  reachable from nothing. Two had keyboard shortcuts nobody could
  discover; the third had no route at all.

  THE CONTROLS ARE SIZED TO THEIR CONTENT. A QSpinBox holding "5 min"
  stretched to 185px because nothing said otherwise, which made the
  General page read as a column of oversized boxes rather than a list of
  settings.

  THE RAIL ICONS MEAN SOMETHING. "Accounts" was illustrated with the
  inbox glyph - a download tray - because it was the closest thing to
  hand, so two unrelated destinations in the same product carried related
  imagery. Every rail entry now has an icon drawn for it.
"""

from __future__ import annotations

import logging
import shutil

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__, config
from app.services.account_manager import AccountManager
from app.ui import theme as t
from app.ui.components.dropdown import Dropdown
from app.ui.components.primitives import Button, Rule, Variant
from app.ui.components.section_header import DialogHeading, SectionHeader
from app.ui.components.theme_toggle import ThemeToggle
from app.ui.components.toggle import Toggle
from app.ui.svg_icon import icon_set

log = logging.getLogger(__name__)

# Wide enough for "Comfortable" and "5 min" without becoming a banner.
_CONTROL_WIDTH = 150


def _panel(*rows: QWidget) -> QWidget:
    """A group of settings, separated by ONE hairline each.

    THE SEPARATORS WERE DOUBLED. This inserted a Rule between every pair of
    rows while the stylesheet independently gave #settingsRow a
    border-bottom - so three rows drew five hairlines, and the two that
    landed together between each pair read as one heavier, slightly
    uneven line. Nobody would report it; it is exactly the sort of thing
    that makes a surface feel not-quite-made.

    The row's own border is the mechanism that survives, because it also
    closes the group under the last row - which a between-rows divider by
    definition cannot do, and which is what gives the panel a bottom edge.
    """
    panel = QWidget()
    panel.setObjectName("settingsPanel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    for row in rows:
        layout.addWidget(row)
    return panel


def _row(label_text: str, control: QWidget, description: str = "") -> QWidget:
    """One setting: its name, what it does, and the control.

    THE DESCRIPTION IS NOT DECORATION. Without it a row says "Messages
    shown per view: 100" and leaves the reader to guess whether that is a
    download limit, a cap on what is kept, or a page size - three answers
    with very different consequences. A setting that cannot explain itself
    gets changed by guesswork, or not at all.
    """
    row = QWidget()
    row.setObjectName("settingsRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
    layout.setSpacing(t.SPACE_XL)

    text = QVBoxLayout()
    text.setSpacing(t.SPACE_XXS)
    label = QLabel(label_text)
    label.setFont(t.make_font("field_value"))
    label.setBuddy(control)
    text.addWidget(label)
    if description:
        hint = QLabel(description)
        hint.setFont(t.make_font("caption"))
        t.role(hint, "tertiary")
        hint.setWordWrap(True)
        text.addWidget(hint)
    layout.addLayout(text, stretch=1)

    # AlignTop, not AlignVCenter: against a two-line description the
    # control would otherwise float against the middle of the text block
    # instead of lining up with the setting's name, which is what it
    # belongs to.
    layout.addWidget(control, 0, Qt.AlignmentFlag.AlignTop)
    return row


class _RailItem(QToolButton):
    """One entry in the settings rail: icon above a short label, checked
    when its page is active."""

    def __init__(self, icon_name: str, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsRailItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._icon_name = icon_name
        self.setIconSize(QSize(20, 20))
        self.setText(label)
        self.setAccessibleName(label)
        self.setFont(t.make_font("caption"))
        self.setFixedWidth(86)
        self.retheme()

    def retheme(self) -> None:
        self.setIcon(icon_set(
            self._icon_name, 20, normal=t.ICON_SECONDARY,
            active=t.ICON_ACTIVE, selected=t.ICON_SELECTED,
        ))


def _page(*widgets: QWidget) -> QWidget:
    page = QWidget()
    col = QVBoxLayout(page)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(t.SPACE_MD)
    for w in widgets:
        col.addWidget(w)
    col.addStretch(1)
    return page


def _spin(*, low: int, high: int, step: int, suffix: str, value: int) -> QSpinBox:
    box = QSpinBox()
    box.setObjectName("settingsControl")
    box.setRange(low, high)
    box.setSingleStep(step)
    box.setSuffix(suffix)
    box.setValue(value)
    box.setFixedWidth(_CONTROL_WIDTH)
    box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return box


class SettingsDialog(QDialog):
    """Emits accepted() after saving; the caller then re-reads Settings.

    The theme is the exception to "nothing happens until Save": it is
    requested live through theme_requested (with the control's global
    position, so the change can spread from it), and reverted on Cancel.
    """

    #: (mode, global QPoint the request came from, or None for no place)
    theme_requested = Signal(str, object)

    def __init__(self, settings: config.Settings, manager: AccountManager,
                 parent=None, *, release_notes=None):
        super().__init__(parent)
        self.settings = settings
        self.manager = manager
        self.accounts_changed = False
        # What to put back if the dialog is cancelled after a live change.
        self._theme_on_open = str(settings.get("theme_mode") or "dark")

        self.setWindowTitle("Settings")
        self.setMinimumSize(720, 520)
        self.setObjectName("settingsDialog")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(t.SPACE_XL, t.SPACE_LG, t.SPACE_XL, t.SPACE_LG)
        outer.setSpacing(t.SPACE_LG)

        # -- header (stays put across every page)
        header = QHBoxLayout()
        header.setSpacing(t.SPACE_SM)
        header.addWidget(DialogHeading("Settings"))
        header.addStretch(1)
        cancel_btn = Button("Cancel", Variant.SECONDARY)
        cancel_btn.clicked.connect(self.reject)
        header.addWidget(cancel_btn)
        save_btn = Button(" Save", Variant.PRIMARY)
        save_btn.set_icon("check")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        header.addWidget(save_btn)
        outer.addLayout(header)

        # -- rail + pages
        body = QHBoxLayout()
        body.setSpacing(t.SPACE_XL)

        rail_col = QVBoxLayout()
        rail_col.setSpacing(t.SPACE_XS)
        self._rail_group = QButtonGroup(self)
        self._rail_group.setExclusive(True)
        rail_specs = [
            ("settings", "General"),
            ("contrast", "Appearance"),
            ("lock", "Google"),
            ("person", "Accounts"),
        ]
        if release_notes is not None:
            rail_specs.append(("changelog", "Changelog"))
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
        self.stack.addWidget(self._build_appearance_page())
        self.stack.addWidget(self._build_google_page())
        self.stack.addWidget(self._build_accounts_page())
        self.changelog = None
        if release_notes is not None:
            from app.ui.components.changelog import ChangelogPage
            self.changelog = ChangelogPage(release_notes)
            self.stack.addWidget(self.changelog)
        body.addWidget(self.stack, stretch=1)
        outer.addLayout(body, stretch=1)

        for i, btn in enumerate(rail_buttons):
            btn.clicked.connect(lambda _=False, idx=i: self._show_page(idx))
        rail_buttons[0].setChecked(True)

        outer.addWidget(Rule())
        version_label = QLabel(f"{APP_NAME} v{__version__}")
        version_label.setFont(t.make_font("caption"))
        t.role(version_label, "tertiary")
        outer.addWidget(version_label)

    def _show_page(self, index: int) -> None:
        """Instant. No transition, and that is the considered choice.

        This faded the incoming page in over DURATION_FAST, and the cost
        was easy to see the moment it was rendered: the page is invisible
        for the first half of the fade, so clicking a rail entry answered
        with an empty panel and then the content. Switching rail entries is
        navigation between siblings, not a change of context - the checked
        state on the rail has already said what happened, and the content
        arriving at the same instant is what makes the switch feel
        immediate rather than merely quick.

        PRODUCT.md: nothing moves without a reason a user could name. There
        is no reason here beyond "a transition would be nice", which is the
        definition of decoration.
        """
        if index == self.stack.currentIndex():
            return
        self.stack.setCurrentIndex(index)

    # ------------------------------------------------------------------ pages

    def _build_general_page(self) -> QWidget:
        self.interval_spin = _spin(
            low=1, high=120, step=1, suffix=" min",
            value=int(self.settings.get("sync_interval_minutes")),
        )
        self.shown_spin = _spin(
            low=100, high=10000, step=100, suffix="",
            value=int(self.settings.get("messages_shown")),
        )
        self.notify_toggle = Toggle()
        self.notify_toggle.setAccessibleName("Desktop notifications for new mail")
        self.notify_toggle.setChecked(
            bool(self.settings.get("notifications_enabled"))
        )
        return _page(
            SectionHeader("General"),
            _panel(
                _row("Check for new mail", self.interval_spin,
                     "How often Unified asks each account for new messages. "
                     "Syncing runs in the background and never blocks the "
                     "window."),
                _row("Messages shown per view", self.shown_spin,
                     "How many cached messages a folder renders at once - not "
                     "a limit on what is downloaded. Load more pages through "
                     "the rest without touching the network."),
                _row("Desktop notifications", self.notify_toggle,
                     "A tray notification when a sync finds new mail."),
            ),
        )

    def _build_appearance_page(self) -> QWidget:
        self.theme_toggle = ThemeToggle(self._theme_on_open)
        self.theme_toggle.mode_requested.connect(self._on_theme_requested)

        self.density_dropdown = Dropdown(
            [("Comfortable", False), ("Compact", True)],
            current=bool(self.settings.get("compact_rows")),
        )
        self.density_dropdown.setFixedWidth(_CONTROL_WIDTH)

        self.motion_toggle = Toggle()
        self.motion_toggle.setAccessibleName("Reduce motion")
        self.motion_toggle.setChecked(bool(self.settings.get("reduced_motion")))

        self.pointer_toggle = Toggle()
        self.pointer_toggle.setAccessibleName("Smooth pointer (experimental)")
        self.pointer_toggle.setChecked(bool(self.settings.get("smooth_pointer")))

        return _page(
            SectionHeader("Appearance"),
            _panel(
                _row("Theme", self.theme_toggle,
                     "Light or dark. It changes as soon as you choose, so "
                     "you can judge it here; Cancel puts it back."),
                _row("Message rows", self.density_dropdown,
                     "Comfortable shows the sender, the subject and a line of "
                     "the message. Compact drops the preview line and fits "
                     "about a third more on screen."),
                _row("Reduce motion", self.motion_toggle,
                     "Transitions finish instantly instead of animating. "
                     "Nothing is hidden - every state still changes, it just "
                     "does not travel."),
                _row("Smooth pointer (experimental)", self.pointer_toggle,
                     "Draws the pointer with a glide inside Unified. It runs "
                     "a few hundredths of a second behind the real one, so "
                     "it steps aside over text, while dragging, and when "
                     "motion is reduced."),
            ),
        )

    def _build_google_page(self) -> QWidget:
        google_panel = QWidget()
        google_panel.setObjectName("settingsPanel")
        gv = QVBoxLayout(google_panel)
        gv.setContentsMargins(t.SPACE_MD, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD)
        gv.setSpacing(t.SPACE_MD)
        self.google_label = QLabel()
        self.google_label.setFont(t.make_font("field_value"))
        t.role(self.google_label, "secondary")
        self.google_label.setWordWrap(True)
        self._update_google_label()
        pick = Button("Select credentials.json...", Variant.SECONDARY)
        pick.clicked.connect(self._pick_google_file)
        gv.addWidget(self.google_label)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(pick)
        row.addStretch(1)
        gv.addLayout(row)
        return _page(SectionHeader("Google sign-in"), google_panel)

    def _build_accounts_page(self) -> QWidget:
        accounts_panel = QWidget()
        accounts_panel.setObjectName("settingsPanel")
        av = QVBoxLayout(accounts_panel)
        av.setContentsMargins(t.SPACE_SM, t.SPACE_SM, t.SPACE_SM, t.SPACE_SM)
        av.setSpacing(t.SPACE_MD)
        self.account_list = QListWidget()
        self.account_list.setFrameShape(QListWidget.Shape.NoFrame)
        self.account_list.setAccessibleName("Connected accounts")
        self._reload_accounts()

        # DESTRUCTIVE, AND IT SAYS SO IN THE ERROR HUE RATHER THAN BEING A
        # FILLED RED SLAB - a filled red button is the loudest thing on any
        # screen it appears on, which is the wrong emphasis for an action
        # nobody should be encouraged toward.
        remove_btn = Button("Remove selected account", Variant.DESTRUCTIVE)
        remove_btn.set_icon("trash")
        remove_btn.clicked.connect(self._remove_selected)
        remove_row = QHBoxLayout()
        remove_row.setContentsMargins(0, 0, 0, 0)
        remove_row.addWidget(remove_btn)
        remove_row.addStretch(1)

        av.addWidget(self.account_list, stretch=1)
        av.addLayout(remove_row)
        return _page(SectionHeader("Connected accounts"), accounts_panel)

    # ------------------------------------------------------------------ misc

    def _update_google_label(self) -> None:
        if config.google_client_secrets_path().exists():
            self.google_label.setText(
                "An OAuth client is configured. Gmail accounts can be added."
            )
        else:
            self.google_label.setText(
                "Not configured. Download an OAuth client (type 'Desktop app') "
                "from the Google Cloud Console with the Gmail API enabled, "
                "then select the credentials.json file here. Unified never "
                "sees your Google password."
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
            # It used to do nothing at all with no selection, which reads
            # as a broken control rather than an unmet precondition.
            QMessageBox.information(
                self, "No account selected",
                "Select an account in the list first.",
            )
            return
        account_id = item.data(0x0100)
        reply = QMessageBox.question(
            self,
            "Remove account",
            f"Remove {item.text()} and its cached messages from this machine?\n\n"
            "The account itself is not affected and nothing is deleted at "
            "your provider.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.remove_account(account_id)
            self.accounts_changed = True
            self._reload_accounts()

    def _on_theme_requested(self, mode: str) -> None:
        centre = self.theme_toggle.rect().center()
        self.theme_requested.emit(mode, self.theme_toggle.mapToGlobal(centre))

    def reject(self) -> None:
        # Put back a theme that was only being tried. From the dialog's
        # centre rather than the control: Cancel is not the toggle.
        if self.theme_toggle.mode() != self._theme_on_open:
            self.theme_toggle.set_mode(self._theme_on_open)
            self.theme_requested.emit(self._theme_on_open, None)
        super().reject()

    def _save(self) -> None:
        self.settings.set("sync_interval_minutes", self.interval_spin.value())
        self.settings.set("notifications_enabled", self.notify_toggle.isChecked())
        self.settings.set("messages_shown", self.shown_spin.value())
        self.settings.set("theme_mode", self.theme_toggle.mode())
        self.settings.set("compact_rows", bool(self.density_dropdown.value()))
        self.settings.set("reduced_motion", bool(self.motion_toggle.isChecked()))
        self.settings.set("smooth_pointer", bool(self.pointer_toggle.isChecked()))
        self.accept()

"""The single application stylesheet, rendered from semantic tokens.

There is exactly one QSS source in Unified, and it is this string. No
widget calls `setStyleSheet` with a hardcoded color; components declare
*intent* through dynamic properties (`variant`, `size`, `tone`, `role`)
and the selectors below decide what that intent looks like in the active
theme.

Placeholders are `$name` and are resolved from a map built out of
`palette.Palette` and `tokens`. An unknown placeholder raises at render
time rather than shipping a stylesheet with a literal `$typo` in it - a
mistake QSS otherwise swallows silently, taking the whole rule with it.
"""

from __future__ import annotations

from dataclasses import fields
from string import Template

from app.ui.design import tokens
from app.ui.design.palette import Palette


def build_variables(palette: Palette) -> dict[str, str]:
    """Every name the template may reference: color roles by their role
    name, plus the dimensional scales as `space_*`, `radius_*`, etc."""
    variables: dict[str, str] = {}
    for f in fields(palette):
        value = getattr(palette, f.name)
        if isinstance(value, str):
            variables[f.name] = value

    for name in dir(tokens):
        if name.startswith("_") or name != name.upper():
            continue
        value = getattr(tokens, name)
        if isinstance(value, (int, float, str)):
            variables[name.lower()] = str(value)

    variables["font_family"] = tokens.FONT_FAMILIES_CSS
    variables["font_family_mono"] = tokens.FONT_FAMILIES_MONO_CSS
    return variables


class _StrictTemplate(Template):
    delimiter = "$"


_QSS = r"""
/* ===================================================================
   Base
   =================================================================== */
* {
    font-family: $font_family;
    font-size: ${size_md}px;
    color: $text_primary;
    outline: none;
}
QWidget { background: transparent; color: $text_primary; }

/* Listed after the bare QWidget rule on purpose: Qt breaks specificity
   ties between "QMainWindow, QDialog" and "QWidget" by source order, and
   a transparent top-level window paints as opaque black wherever no
   styled child covers it. */
QMainWindow, QDialog { background: $canvas; }
QStackedWidget { background: transparent; }
QWidget#appRoot { background: $canvas; }

QLabel { background: transparent; }
QLabel[tone="secondary"], QLabel#secondary { color: $text_secondary; }
QLabel[tone="tertiary"], QLabel#tertiary { color: $text_tertiary; }
QLabel[tone="danger"] { color: $danger_fg; }
QLabel[tone="success"] { color: $success_fg; }
QLabel[tone="warning"] { color: $warning_fg; }
QLabel[tone="accent"] { color: $accent_fg; }
QLabel[role="overline"] {
    color: $text_tertiary;
    font-size: ${size_2xs}px;
    font-weight: $weight_bold;
    letter-spacing: 0.9px;
}
QLabel:disabled { color: $text_disabled; }

/* ===================================================================
   Buttons - one control, five appearances, selected by property
   =================================================================== */
QPushButton, QToolButton {
    background: $surface;
    border: ${stroke_thin}px solid $border_strong;
    border-radius: ${radius_sm}px;
    padding: 0 ${space_lg}px;
    min-height: ${control_md}px;
    color: $text_primary;
    font-weight: $weight_semibold;
}
QPushButton:hover, QToolButton:hover {
    background: $surface_hover;
    border-color: $border_strong;
}
QPushButton:pressed, QToolButton:pressed { background: $surface_active; }
QPushButton:focus, QToolButton:focus { border-color: $focus_ring; }
QPushButton:disabled, QToolButton:disabled {
    color: $text_disabled;
    border-color: $border;
    background: $surface;
}

QPushButton[variant="primary"] {
    background: $accent_solid;
    color: $text_on_accent;
    border: ${stroke_thin}px solid $accent_solid;
}
QPushButton[variant="primary"]:hover {
    background: $accent_solid_hover;
    border-color: $accent_solid_hover;
}
QPushButton[variant="primary"]:pressed {
    background: $accent_solid_pressed;
    border-color: $accent_solid_pressed;
}
QPushButton[variant="primary"]:disabled {
    background: $surface_active;
    color: $text_disabled;
    border-color: $border;
}

QPushButton[variant="danger"] {
    background: $danger_strong;
    color: $text_on_accent;
    border: ${stroke_thin}px solid $danger_strong;
}
QPushButton[variant="danger"]:hover { background: $danger_fg; border-color: $danger_fg; }
QPushButton[variant="danger"]:pressed { background: $danger_strong; }
QPushButton[variant="danger"]:disabled {
    background: $surface_active;
    color: $text_disabled;
    border-color: $border;
}

/* A destructive action that is not the point of the screen. On a
   settings page a solid red button out-shouts Save, which is the button
   the user is actually there to press. */
QPushButton[variant="danger_quiet"] {
    background: transparent;
    color: $danger_fg;
    border: ${stroke_thin}px solid $border_strong;
}
QPushButton[variant="danger_quiet"]:hover {
    background: $danger_bg;
    border-color: $danger_fg;
}
QPushButton[variant="danger_quiet"]:pressed { background: $danger_bg; }
QPushButton[variant="danger_quiet"]:disabled {
    color: $text_disabled;
    border-color: $border;
    background: transparent;
}

QPushButton[variant="subtle"], QToolButton[variant="subtle"] {
    background: transparent;
    border: ${stroke_thin}px solid transparent;
    color: $text_secondary;
    font-weight: $weight_medium;
}
QPushButton[variant="subtle"]:hover, QToolButton[variant="subtle"]:hover {
    background: $surface_hover;
    color: $text_primary;
}
QPushButton[variant="subtle"]:pressed, QToolButton[variant="subtle"]:pressed {
    background: $surface_active;
}
QPushButton[variant="subtle"]:checked, QToolButton[variant="subtle"]:checked {
    background: $accent_subtle;
    color: $accent_fg;
    border-color: $accent;
}
QPushButton[variant="subtle"]:focus, QToolButton[variant="subtle"]:focus {
    border-color: $focus_ring;
}
QPushButton[variant="subtle"]:disabled, QToolButton[variant="subtle"]:disabled {
    color: $text_disabled;
    background: transparent;
}

QPushButton[variant="link"] {
    background: transparent;
    border: ${stroke_thin}px solid transparent;
    color: $accent_fg;
    padding: 0 ${space_xs}px;
    font-weight: $weight_semibold;
}
QPushButton[variant="link"]:hover { color: $accent_hover; text-decoration: underline; }
QPushButton[variant="link"]:focus { border-color: $focus_ring; }
QPushButton[variant="link"]:disabled { color: $text_disabled; }

/* Icon-only actions: square, no label, no padding asymmetry. */
QPushButton[shape="icon"], QToolButton[shape="icon"] {
    padding: 0;
    min-width: ${control_md}px;
    max-width: ${control_md}px;
    min-height: ${control_md}px;
    max-height: ${control_md}px;
    background: transparent;
    border: ${stroke_thin}px solid transparent;
}
QPushButton[shape="icon"]:hover, QToolButton[shape="icon"]:hover {
    background: $surface_hover;
}
QPushButton[shape="icon"]:pressed, QToolButton[shape="icon"]:pressed {
    background: $surface_active;
}
QPushButton[shape="icon"]:checked, QToolButton[shape="icon"]:checked {
    background: $accent_subtle;
    border-color: $accent;
}
QPushButton[shape="icon"]:focus, QToolButton[shape="icon"]:focus {
    border-color: $focus_ring;
}

/* Keyboard focus. Installed by components/focus.py so it appears for
   Tab/shortcut focus but not for a plain mouse click. The extra border
   pixel is paid for out of the padding, so nothing on the row moves. */
QPushButton[kbfocus="true"], QToolButton[kbfocus="true"],
QLineEdit[kbfocus="true"], QPlainTextEdit[kbfocus="true"],
QTextEdit[kbfocus="true"], QSpinBox[kbfocus="true"],
QComboBox[kbfocus="true"], QCheckBox[kbfocus="true"] {
    border: ${stroke_focus}px solid $focus_ring;
}
QPushButton[kbfocus="true"] { padding: 0 ${space_sm}px; }
QPushButton[shape="icon"][kbfocus="true"],
QToolButton[shape="icon"][kbfocus="true"] { padding: 0; }
QLineEdit[kbfocus="true"], QSpinBox[kbfocus="true"], QComboBox[kbfocus="true"] {
    padding: 0 ${space_sm}px;
}
QListView[kbfocus="true"], QListWidget[kbfocus="true"],
QTreeWidget[kbfocus="true"] { border: ${stroke_focus}px solid $focus_ring; }

/* An icon-only *primary* action is still the primary action. Without
   this the generic icon rule below would strip Compose of its fill the
   moment the window got narrow enough to drop its label. */
QPushButton[variant="primary"][shape="icon"] {
    background: $accent_solid;
    border-color: $accent_solid;
}
QPushButton[variant="primary"][shape="icon"]:hover {
    background: $accent_solid_hover;
    border-color: $accent_solid_hover;
}
QPushButton[variant="primary"][shape="icon"]:pressed {
    background: $accent_solid_pressed;
}

QPushButton[size="sm"], QToolButton[size="sm"] {
    min-height: ${control_sm}px;
    padding: 0 ${space_md}px;
    font-size: ${size_sm}px;
}
QPushButton[size="lg"] {
    min-height: ${control_lg}px;
    padding: 0 ${space_xl}px;
}
QPushButton[shape="icon"][size="sm"], QToolButton[shape="icon"][size="sm"] {
    min-width: ${control_sm}px; max-width: ${control_sm}px;
    min-height: ${control_sm}px; max-height: ${control_sm}px;
}

/* ===================================================================
   Text inputs
   =================================================================== */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {
    background: $surface;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_sm}px;
    padding: 0 ${space_md}px;
    min-height: ${control_md}px;
    selection-background-color: $accent_solid;
    selection-color: $text_on_accent;
    color: $text_primary;
}
QPlainTextEdit, QTextEdit { padding: ${space_md}px; }
QLineEdit:hover, QSpinBox:hover, QComboBox:hover { border-color: $border_strong; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QComboBox:focus {
    border: ${stroke_thick}px solid $focus_ring;
    padding: 0 ${space_sm}px;
}
QPlainTextEdit:focus, QTextEdit:focus { padding: ${space_sm}px; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled,
QPlainTextEdit:disabled, QTextEdit:disabled {
    color: $text_disabled;
    background: $surface;
    border-color: $border_subtle;
}
QLineEdit[invalid="true"], QSpinBox[invalid="true"], QComboBox[invalid="true"] {
    border-color: $danger_fg;
}
QLineEdit[readOnly="true"] { background: $canvas; color: $text_secondary; }

QLineEdit[shape="pill"] {
    border-radius: ${radius_pill}px;
    padding: 0 ${space_lg}px;
}
QLineEdit[shape="pill"]:focus { padding: 0 ${space_md}px; }
QLineEdit[surface="raised"] { background: $surface_hover; border-color: transparent; }
QLineEdit[surface="raised"]:hover { border-color: $border; }

/* Real, styled steppers. Hiding them entirely (width: 0) leaves a
   number field that can only be changed by typing, which is a usability
   regression dressed up as minimalism. */
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    width: ${space_2xl}px;
    border: none;
    border-left: ${stroke_thin}px solid $border;
    background: transparent;
}
QSpinBox::up-button { subcontrol-position: top right; border-bottom: none; }
QSpinBox::down-button { subcontrol-position: bottom right; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: $surface_hover; }
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed { background: $surface_active; }
QSpinBox::up-arrow {
    image: url($chevron_up_asset);
    width: ${icon_xs}px; height: ${icon_xs}px;
}
QSpinBox::down-arrow {
    image: url($chevron_asset);
    width: ${icon_xs}px; height: ${icon_xs}px;
}
QComboBox::drop-down { border: none; width: ${space_3xl}px; background: transparent; }
QComboBox::down-arrow {
    image: url($chevron_asset);
    width: ${icon_xs}px;
    height: ${icon_xs}px;
    margin-right: ${space_md}px;
}
QComboBox QAbstractItemView {
    background: $overlay;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_md}px;
    padding: ${space_xs}px;
    selection-background-color: $selected;
    selection-color: $text_primary;
    outline: none;
}

/* ===================================================================
   Custom dropdown (components/dropdown.py)
   =================================================================== */
QWidget#dropdownButton {
    background: $surface;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_sm}px;
}
QWidget#dropdownButton:hover { border-color: $border_strong; background: $surface_hover; }
QWidget#dropdownButton[focused="true"] { border: ${stroke_thick}px solid $focus_ring; }
QFrame#dropdownPopup {
    background: $overlay;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_md}px;
}
QPushButton#dropdownOption {
    background: transparent;
    border: ${stroke_thin}px solid transparent;
    border-radius: ${radius_xs}px;
    padding: 0 ${space_md}px;
    min-height: ${control_md}px;
    text-align: left;
    color: $text_primary;
    font-weight: $weight_regular;
}
QPushButton#dropdownOption:hover { background: $surface_hover; }
QPushButton#dropdownOption:focus { border-color: $focus_ring; }
QPushButton#dropdownOption[selected="true"] {
    background: $accent_subtle;
    color: $accent_fg;
    font-weight: $weight_semibold;
}

/* ===================================================================
   Application shell
   =================================================================== */
QWidget#commandBar {
    background: $sidebar;
    border-bottom: ${stroke_thin}px solid $border;
}
QWidget#sidebar {
    background: $sidebar;
    border-right: ${stroke_thin}px solid $border;
}
QWidget#listPane { background: $canvas; }
QWidget#listHeader {
    background: $canvas;
    border-bottom: ${stroke_thin}px solid $border;
}
QWidget#readerPane {
    background: $surface;
    border-left: ${stroke_thin}px solid $border;
}
QWidget#readerHeader {
    background: $surface;
    border-bottom: ${stroke_thin}px solid $border_subtle;
}
QWidget#readerFooter {
    background: $surface;
    border-top: ${stroke_thin}px solid $border_subtle;
}

/* Sidebar navigation. Selection is a tinted fill *and* a painted accent
   bar (NavItem draws the bar): tint alone reads as hover at a glance. */
QPushButton#navItem, QPushButton#navPill {
    background: transparent;
    border: ${stroke_thin}px solid transparent;
    border-radius: ${radius_md}px;
    padding: 0 ${space_md}px 0 ${space_xl}px;
    text-align: left;
    color: $text_secondary;
    font-weight: $weight_medium;
    min-height: ${tab_height}px;
}
QPushButton#navItem:hover, QPushButton#navPill:hover {
    background: $surface_hover;
    color: $text_primary;
}
QPushButton#navItem:checked, QPushButton#navPill:checked {
    background: $selected;
    color: $text_primary;
    font-weight: $weight_semibold;
}
QPushButton#navItem:focus, QPushButton#navPill:focus { border-color: $focus_ring; }
QPushButton#navItem:disabled, QPushButton#navPill:disabled { color: $text_disabled; }

QWidget#accountItem { background: transparent; border-radius: ${radius_md}px; }
QWidget#accountItem[state="hover"] { background: $surface_hover; }
QWidget#accountItem[state="selected"] { background: $selected; }
QLabel#accountEmail { color: $text_primary; font-weight: $weight_semibold; }

/* Count badges. The only pill shapes in the product. */
QLabel[role="badge"] {
    background: $surface_active;
    color: $text_secondary;
    border-radius: ${radius_pill}px;
    padding: 0 ${space_sm}px;
    min-width: ${space_xl}px;
    font-size: ${size_2xs}px;
    font-weight: $weight_bold;
}
QLabel[role="badge"][tone="accent"] { background: $accent_solid; color: $text_on_accent; }
QLabel[role="badge"][tone="quiet"] { background: transparent; color: $text_tertiary; }

/* ===================================================================
   Message list
   =================================================================== */
QListView#emailList {
    background: $canvas;
    border: none;
    padding: ${space_xs}px ${space_sm}px;
}
QListView { background: $surface; border: none; outline: none; }

QTreeWidget, QListWidget, QTreeView, QTableView {
    background: $surface;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_sm}px;
    outline: none;
    alternate-background-color: $canvas;
    color: $text_primary;
}
QListWidget::item, QTreeWidget::item {
    border: none;
    border-radius: ${radius_xs}px;
    padding: ${space_sm}px ${space_md}px;
}
QListWidget::item:hover, QTreeWidget::item:hover { background: $surface_hover; }
QListWidget::item:selected, QTreeWidget::item:selected {
    background: $selected;
    color: $text_primary;
}
QHeaderView::section {
    background: $canvas;
    border: none;
    border-bottom: ${stroke_thin}px solid $border;
    padding: ${space_sm}px;
    font-weight: $weight_semibold;
    color: $text_secondary;
}

/* ===================================================================
   Surfaces: cards, panels, grouped settings
   =================================================================== */
QWidget[role="card"] {
    background: $surface;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_lg}px;
}
QWidget[role="card"]:hover { border-color: $border_strong; }
QWidget[role="card"][state="selected"] {
    background: $accent_subtle;
    border-color: $accent;
}
QWidget[role="panel"], QWidget#settingsPanel {
    background: $surface;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_lg}px;
}
QWidget[role="inset"] {
    background: $canvas;
    border: ${stroke_thin}px solid $border_subtle;
    border-radius: ${radius_md}px;
}
QFrame[role="divider"] { background: $border_subtle; border: none; max-height: 1px; }
QFrame[role="divider"][orientation="vertical"] { max-width: 1px; max-height: 16777215px; }

QWidget#settingsRow { background: transparent; }
QWidget#settingsRow:hover { background: $surface_hover; }

/* Message-level banners (blocked images, sync failure, offline). */
QWidget[role="banner"] {
    background: $canvas;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_md}px;
}
QWidget[role="banner"][tone="warning"] { background: $warning_bg; border-color: $warning_fg; }
QWidget[role="banner"][tone="danger"] { background: $danger_bg; border-color: $danger_fg; }
QWidget[role="banner"][tone="info"] { background: $info_bg; border-color: $accent; }
QWidget[role="banner"][tone="success"] { background: $success_bg; border-color: $success_fg; }

QWidget[role="chip"] {
    background: $surface_hover;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_sm}px;
}
QWidget[role="chip"][tone="warning"] { border-color: $warning_fg; background: $warning_bg; }
QWidget[role="chip"][tone="danger"] { border-color: $danger_fg; background: $danger_bg; }
QWidget[role="chip"] QLabel { font-size: ${size_sm}px; color: $text_secondary; }

/* ===================================================================
   Menus, tooltips, scrollbars, splitters
   =================================================================== */
QMenu {
    background: $overlay;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_md}px;
    padding: ${space_xs}px;
}
QMenu::item {
    padding: ${space_sm}px ${space_3xl}px ${space_sm}px ${space_lg}px;
    border-radius: ${radius_xs}px;
    color: $text_primary;
}
QMenu::item:selected { background: $surface_hover; }
QMenu::item:disabled { color: $text_disabled; }
QMenu::separator { height: 1px; background: $border_subtle; margin: ${space_xs}px ${space_md}px; }
QMenu::icon { padding-left: ${space_md}px; }

QToolTip {
    background: $overlay;
    color: $text_primary;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_xs}px;
    padding: ${space_xs}px ${space_md}px;
}

QScrollBar:vertical { background: transparent; width: ${space_md}px; margin: 0; }
QScrollBar::handle:vertical {
    background: $border_strong;
    border-radius: ${space_xs}px;
    min-height: ${space_3xl}px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover { background: $text_tertiary; }
QScrollBar:horizontal { background: transparent; height: ${space_md}px; margin: 0; }
QScrollBar::handle:horizontal {
    background: $border_strong;
    border-radius: ${space_xs}px;
    min-width: ${space_3xl}px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover { background: $text_tertiary; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QSplitter::handle { background: transparent; width: 1px; }
QSplitter::handle:hover { background: $accent; }
QScrollArea { background: transparent; border: none; }

/* ===================================================================
   Progress, checkboxes, status bar, console
   =================================================================== */
QProgressBar {
    border: none;
    border-radius: 2px;
    background: $surface_active;
    text-align: center;
    min-height: 4px;
    max-height: 4px;
}
QProgressBar::chunk { background: $accent; border-radius: 2px; }

QCheckBox, QRadioButton { background: transparent; spacing: ${space_md}px; }
/* The switch paints its own track and knob; without this Qt draws a
   checkbox indicator on top of it. */
QCheckBox[role="switch"]::indicator {
    width: 0; height: 0; border: none; background: transparent; image: none;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: ${icon_md}px; height: ${icon_md}px;
    border: ${stroke_thin}px solid $border_strong;
    border-radius: ${radius_xs}px;
    background: $surface;
}
QRadioButton::indicator { border-radius: ${icon_md}px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked {
    background: $accent_solid;
    border-color: $accent_solid;
    image: url($check_asset);
}
QRadioButton::indicator:checked { background: $accent_solid; border-color: $accent_solid; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    border-color: $border;
    background: $surface;
}

QStatusBar {
    background: $sidebar;
    border-top: ${stroke_thin}px solid $border;
    color: $text_secondary;
    min-height: ${status_bar_height}px;
}
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $text_secondary; font-size: ${size_sm}px; }

QPlainTextEdit#console {
    border: none;
    border-top: ${stroke_thin}px solid $border;
    background: $canvas;
    color: $text_secondary;
    font-family: $font_family_mono;
    font-size: ${size_sm}px;
    padding: ${space_md}px;
}
QPushButton#consoleFilter {
    background: transparent;
    border: ${stroke_thin}px solid $border;
    border-radius: ${radius_pill}px;
    padding: 0 ${space_lg}px;
    min-height: ${control_xs}px;
    font-size: ${size_xs}px;
    font-weight: $weight_semibold;
    color: $text_secondary;
}
QPushButton#consoleFilter:hover { background: $surface_hover; color: $text_primary; }
QPushButton#consoleFilter:checked {
    background: $accent_subtle;
    border-color: $accent;
    color: $accent_fg;
}

/* ===================================================================
   Reading pane and compose
   =================================================================== */
/* An explicit color (never "transparent") - a QAbstractScrollArea
   viewport can composite a transparent background as opaque black. */
QTextBrowser { border: none; background: $surface; color: $text_primary; }
QTextBrowser#emailBody {
    border: none;
    background: $surface;
    padding: ${space_3xl}px ${space_4xl}px;
}

QWidget#composeFieldRow { border-bottom: ${stroke_thin}px solid $border_subtle; }
QWidget#composeFieldRow[last="true"] { border-bottom: none; }
QLineEdit#composeField {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    min-height: ${control_md}px;
}
QLineEdit#composeField:focus { border: none; padding: 0; }
QPlainTextEdit#composeBody {
    background: transparent;
    border: none;
    padding: 0;
    font-size: ${size_lg}px;
}
QPlainTextEdit#composeBody:focus { border: none; padding: 0; }

/* Settings navigation rail */
QPushButton#settingsRailItem {
    background: transparent;
    border: ${stroke_thin}px solid transparent;
    border-radius: ${radius_md}px;
    padding: 0 ${space_lg}px;
    min-height: ${tab_height}px;
    text-align: left;
    color: $text_secondary;
    font-weight: $weight_medium;
}
QPushButton#settingsRailItem:hover { background: $surface_hover; color: $text_primary; }
QPushButton#settingsRailItem:checked {
    background: $selected;
    color: $text_primary;
    font-weight: $weight_semibold;
}
QPushButton#settingsRailItem:focus { border-color: $focus_ring; }
"""


# QSS cannot draw a shape, so the two image-backed subcontrols
# (QComboBox's chevron, QCheckBox's tick) need real files on disk,
# regenerated per theme so they are never the wrong color after a switch.
def _asset_variables(palette: Palette) -> dict[str, str]:
    from app.ui.svg_icon import theme_asset_url

    return {
        "chevron_asset": theme_asset_url("chevron_down", 12, palette.text_secondary),
        "chevron_up_asset": theme_asset_url("chevron_up", 12, palette.text_secondary),
        "check_asset": theme_asset_url("check", 12, palette.text_on_accent),
    }


def render(palette: Palette) -> str:
    """Render the app stylesheet for `palette`. Raises KeyError if the
    template references a token that does not exist - a typo must fail
    here, not silently delete the rule it appears in."""
    variables = build_variables(palette)
    variables.update(_asset_variables(palette))
    return _StrictTemplate(_QSS).substitute(variables)


# Public name used by app.ui.style; `render_stylesheet` keeps the older
# spelling working for anything that imported it directly.
render_stylesheet = render

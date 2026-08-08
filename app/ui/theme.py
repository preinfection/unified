"""Design system: every color, spacing, radius, typography, icon-size,
control-height, and animation-duration value the UI uses, in one place.

Single source of truth: style.py builds the QSS from these constants, and
the custom-painted widgets (email row delegate, account items) import the
same values directly - so a delegate's hand-painted hover state can never
drift out of sync with what the stylesheet says "hover" means everywhere
else, and no widget invents its own one-off pixel value.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# ---------------------------------------------------------------- backgrounds
# Five elevation steps, each one step lighter than the last - the app never
# needs a widget to guess how "raised" it should look; it picks the surface
# that matches its place in this stack.
BG_APP = "#14161c"        # window / email list background - the floor
BG_SIDEBAR = "#181a21"    # account drawer - one step off the floor
BG_PANEL = "#1c1f27"      # elevated surfaces: cards, inputs, dialogs, menus
BG_HOVER = "#20232c"
BG_SELECTED = "#242a38"
BG_OVERLAY = "#22262f"    # popups/menus/tooltips - between panel and selected

# ------------------------------------------------------------------- borders
BORDER = "#2a2d37"
BORDER_LIGHT = "#363b48"

# --------------------------------------------------------------------- text
TEXT_PRIMARY = "#eef0f3"
TEXT_SECONDARY = "#9aa0ac"
TEXT_TERTIARY = "#6b7180"
TEXT_ON_ACCENT = "#ffffff"

# ------------------------------------------------------------------- accents
ACCENT = "#5b8def"
ACCENT_HOVER = "#7aa4f2"
ACCENT_PRESSED = "#4a7ddb"
ACCENT_SOFT_BG = "#1f2c42"   # tinted background behind a selected pill/row

SUCCESS = "#34c77b"
WARNING = "#e8a53d"
ERROR = "#ef5c5c"
STARRED = "#f0b429"
SECURE = SUCCESS   # encryption/local-storage affordances read as "good"

# Per-status colors used by both the sidebar status dot and the row delegate.
STATUS_COLORS = {
    "syncing": ACCENT,
    "waiting": TEXT_TERTIARY,
    "done": SUCCESS,
    "partial": WARNING,
    "error": ERROR,
    "idle": TEXT_TERTIARY,
}

# ------------------------------------------------------------------ spacing
# A single 4px-based scale, used consistently instead of ad-hoc pixel
# values scattered through each widget's layout code.
SPACE_XXS = 2
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXL = 32
SPACE_XXXL = 48

# -------------------------------------------------------------------- radii
RADIUS_XS = 4     # checkboxes, tiny chips
RADIUS_SM = 6     # inputs, buttons, list rows
RADIUS_MD = 8     # nav pills, menus
RADIUS_LG = 10    # cards
RADIUS_XL = 14    # dialogs, large panels
RADIUS_PILL = 999  # search field, badges, fully-rounded controls

# ------------------------------------------------------------- control sizes
HEIGHT_SM = 28     # compact controls (chips, inline actions)
HEIGHT_MD = 34     # standard buttons/inputs
HEIGHT_LG = 40     # primary actions (Send, Compose)

ICON_SIZE_ROW = 13    # inline row glyphs (star/attachment in the list)
ICON_SIZE_ACTION = 16  # reading-pane/compose action buttons
ICON_SIZE_TOOLBAR = 18
ICON_SIZE_NAV = 17

# --------------------------------------------------------------- animation
DURATION_FAST = 120   # hover/press feedback
DURATION_BASE = 180   # selection changes, panel content swaps
DURATION_SLOW = 260   # panel open/close, dialogs

# --------------------------------------------------------------- typography
# A native Windows 11 font stack: Segoe UI Variable is the modern system
# font (sharper, better spacing than classic Segoe UI); QFont.setFamilies
# falls back through the list automatically on Windows 10 or if the
# variable font isn't installed, so this never needs a runtime OS check.
FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Arial", "sans-serif"]
FONT_FAMILIES_CSS = ", ".join(f'"{f}"' for f in FONT_FAMILIES[:-1]) + ", sans-serif"

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_SEMIBOLD = 600
WEIGHT_BOLD = 700

SIZE_XS = 11
SIZE_SM = 12
SIZE_MD = 13
SIZE_LG = 14
SIZE_XL = 16
SIZE_XXL = 20
SIZE_TITLE = 22

# name -> (pixel size, weight, letter-spacing in px or None)
# Every context that renders text - list rows, dialogs, compose, settings -
# reads its font from here, so "what should a subject line look like"
# has exactly one answer across the whole app.
TYPOGRAPHY: dict[str, tuple[int, int, float | None]] = {
    "app_title": (SIZE_TITLE, WEIGHT_BOLD, None),
    "dialog_heading": (SIZE_XL, WEIGHT_BOLD, None),
    "nav_label": (SIZE_MD, WEIGHT_MEDIUM, None),
    "section_label": (SIZE_XS, WEIGHT_BOLD, 0.8),
    "account_label": (SIZE_MD, WEIGHT_MEDIUM, None),
    "sender": (SIZE_MD, WEIGHT_SEMIBOLD, None),
    "sender_read": (SIZE_MD, WEIGHT_REGULAR, None),
    "subject": (SIZE_SM, WEIGHT_MEDIUM, None),
    "subject_read": (SIZE_SM, WEIGHT_REGULAR, None),
    "preview": (SIZE_SM, WEIGHT_REGULAR, None),
    "timestamp": (SIZE_XS, WEIGHT_REGULAR, None),
    "button": (SIZE_MD, WEIGHT_SEMIBOLD, None),
    "menu_item": (SIZE_MD, WEIGHT_REGULAR, None),
    "field_label": (SIZE_SM, WEIGHT_MEDIUM, None),
    "field_value": (SIZE_MD, WEIGHT_REGULAR, None),
    "body": (SIZE_MD, WEIGHT_REGULAR, None),
    "status": (SIZE_SM, WEIGHT_MEDIUM, None),
    "caption": (SIZE_XS, WEIGHT_REGULAR, None),
}


def make_font(preset: str, *, italic: bool = False) -> QFont:
    """Build a QFont from a named TYPOGRAPHY entry."""
    size, weight, spacing = TYPOGRAPHY[preset]
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    if spacing is not None:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    font.setItalic(italic)
    return font


# --------------------------------------------------------------------- icons
ICON_SECONDARY = TEXT_SECONDARY   # default icon color (inactive)
ICON_ACTIVE = TEXT_PRIMARY        # hovered
ICON_SELECTED = ACCENT            # checked/pressed
ICON_DISABLED = TEXT_TERTIARY


def qcolor(hex_value: str) -> QColor:
    return QColor(hex_value)


# --------------------------------------------------------------- elevation
# Qt Style Sheets have no box-shadow property, so real elevation is done
# with QGraphicsDropShadowEffect. Three presets cover everything the app
# needs: a resting card, a hovering/dragging state, and a modal-level
# surface - rather than each call site inventing its own blur/offset.
SHADOW_PRESETS = {
    "sm": dict(blur=12, y_offset=3, alpha=70),
    "md": dict(blur=24, y_offset=6, alpha=110),
    "lg": dict(blur=40, y_offset=12, alpha=150),
}


def apply_soft_shadow(widget, blur: int = 24, y_offset: int = 6,
                      alpha: int = 110) -> None:
    """Attach a real, soft drop shadow to an elevated surface (cards,
    dialogs). Qt Style Sheets have no box-shadow property, so this is done
    with QGraphicsDropShadowEffect instead of faking depth with borders.
    """
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


def apply_elevation(widget, level: str = "md") -> None:
    """apply_soft_shadow using one of the named SHADOW_PRESETS."""
    apply_soft_shadow(widget, **SHADOW_PRESETS[level])

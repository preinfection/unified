"""Color tokens for the dark theme.

Single source of truth: style.py builds the QSS from these constants, and
the custom-painted widgets (email row delegate, account items) import the
same QColor objects directly - so a delegate's hand-painted hover state
can never drift out of sync with what the stylesheet says "hover" means
everywhere else.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

# ---------------------------------------------------------------- backgrounds
BG_APP = "#14161c"        # window / email list background
BG_SIDEBAR = "#181a21"    # account drawer - one step off the app background
BG_PANEL = "#1c1f27"      # elevated surfaces: preview pane, drawer cards, inputs
BG_HOVER = "#20232c"
BG_SELECTED = "#242a38"
BG_PILL = "#1f2937"       # unselected nav pill / tag background

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
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

# --------------------------------------------------------------- typography
# Weight tiers used for hierarchy instead of relying on color/size alone -
# matches how native mail clients distinguish sender/subject/snippet.
WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_SEMIBOLD = 600
WEIGHT_BOLD = 700

# --------------------------------------------------------------------- icons
ICON_SECONDARY = TEXT_SECONDARY   # default icon color (inactive)
ICON_ACTIVE = TEXT_PRIMARY        # hovered
ICON_SELECTED = ACCENT            # checked/pressed
ICON_DISABLED = TEXT_TERTIARY


def qcolor(hex_value: str) -> QColor:
    return QColor(hex_value)


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

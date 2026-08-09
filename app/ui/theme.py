"""Design system: every color, spacing, radius, typography, icon-size,
control-height, and animation-duration value the UI uses, in one place.

Single source of truth: style.py builds the QSS from these constants, and
the custom-painted widgets (email row delegate, account items) import the
same values directly - so a delegate's hand-painted hover state can never
drift out of sync with what the stylesheet says "hover" means everywhere
else, and no widget invents its own one-off pixel value.

Palette and scale rebuilt against the OvertimeUI visual reference: darker,
more saturated elevation ramp (closer to the reference's near-black
bg/bgAlt/surface/surfaceHi steps than the previous charcoal-gray version),
a brighter, glow-capable accent, and a bumped-up radius/control-size scale
- the reference reads as a rounder, more confident, more deliberately
layered UI than a flat "dark mode" palette, and this is the translation of
that into a professional desktop app rather than a copy of its exact look.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# ---------------------------------------------------------------- backgrounds
# Five elevation steps, each one step lighter than the last - the app never
# needs a widget to guess how "raised" it should look; it picks the surface
# that matches its place in this stack. Pulled noticeably darker/cooler than
# the previous palette, matching the reference's near-black bg/bgAlt/surface
# ramp rather than a mid-gray "charcoal" dark theme.
# Values below are the reference's elevation ramp translated 1:1 from its
# defaultTheme(): bg(11,12,17) bgAlt(16,18,25) surface(26,29,40)
# surfaceHi(38,43,58). Unified needs one extra step the reference doesn't
# (a distinct selected-row tint), which sits between surface and surfaceHi
# with an accent bias.
BG_APP = "#0b0c11"        # reference `bg`      - window floor / email list
BG_SIDEBAR = "#101219"    # reference `bgAlt`   - sidebar, panel bodies
BG_PANEL = "#1a1d28"      # reference `surface` - cards, inputs, controls at rest
BG_HOVER = "#262b3a"      # reference `surfaceHi` - hover / active
BG_SELECTED = "#1f2a44"   # accent-biased selection tint (Unified-specific)
BG_OVERLAY = "#151822"    # popups/menus/tooltips - just above bgAlt

# ------------------------------------------------------------------- borders
BORDER = "#2a2f3e"        # reference `border`   - low-contrast hairlines
BORDER_LIGHT = "#40485c"  # reference `borderHi` - focused / hovered edges

# --------------------------------------------------------------------- text
TEXT_PRIMARY = "#eceef6"    # reference `text`
TEXT_SECONDARY = "#8a91a2"  # reference `textDim`
TEXT_TERTIARY = "#646b7d"   # one step below textDim for tertiary metadata
TEXT_ON_ACCENT = "#ffffff"

# ------------------------------------------------------------------- accents
# Exactly the reference's accent / accentDim / accentGlow.
ACCENT = "#60a5ff"
ACCENT_HOVER = "#8cbcff"
ACCENT_PRESSED = "#365c96"   # reference `accentDim`
ACCENT_GLOW = "#78b4ff"      # reference `accentGlow`
ACCENT_SOFT_BG = "#1a2740"   # tinted background behind a selected pill/row

SUCCESS = "#34c77b"
WARNING = "#e8a53d"
ERROR = "#eb5c60"   # reference `danger`
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
# Matched to the reference's actual corner() calls: 4 on small indicators,
# 6 on controls/options, 8 on panel bodies and tab strips, 10 on the
# window panel itself. The previous scale had drifted noticeably rounder
# than the reference, which read as a softer, less precise product.
RADIUS_XS = 4     # checkboxes, tiny chips, menu items
RADIUS_SM = 6     # inputs, buttons, list rows, dropdown options
RADIUS_MD = 8     # nav pills, menus, panel bodies, toasts
RADIUS_LG = 10    # cards, the main window panel
RADIUS_XL = 12    # dialogs, large panels
RADIUS_PILL = 999  # search field, badges, fully-rounded controls

# ------------------------------------------------------------- control sizes
# The reference runs denser than Unified had drifted to: 26px control
# rows, 30px tab buttons, 36px title bar. These keep desktop-comfortable
# hit targets while pulling back toward that density.
HEIGHT_SM = 26     # compact controls (chips, inline actions) - reference row
HEIGHT_MD = 32     # standard buttons/inputs
HEIGHT_LG = 38     # primary actions (Send, Compose)

# Structural tokens lifted from the reference's defaultStyle().
TAB_HEIGHT = 30        # per-nav-item height
BODY_PADDING = 12      # inner padding of a content page
ROW_SPACING = 2        # vertical gap between stacked control rows
TITLE_HEIGHT = 36      # dialog/window header band
SIDEBAR_WIDTH = 232    # reference tabWidth=120 scaled for real email addresses

ICON_SIZE_ROW = 13    # inline row glyphs (star/attachment in the list)
ICON_SIZE_ACTION = 16  # reading-pane/compose action buttons
ICON_SIZE_TOOLBAR = 18
ICON_SIZE_NAV = 17

# --------------------------------------------------------------- animation
# The reference's shared tween triple (T_FAST/T_NORMAL/T_SLOW), in ms.
# Its easing is Quint/Out throughout; QEasingCurve.OutQuint is the direct
# equivalent and is what the animated components here use.
DURATION_FAST = 120   # hover/press feedback
DURATION_BASE = 180   # selection changes, panel content swaps
DURATION_SLOW = 280   # panel open/close, dialogs

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


def apply_glow(widget, color: str = ACCENT, blur: int = 28, alpha: int = 130) -> None:
    """A soft colored halo instead of a neutral black drop shadow - the
    reference's "ambient light behind the panel" technique, used sparingly
    on the app's one or two most important surfaces (the primary compose
    action, the active sidebar item) rather than everywhere, so it reads
    as emphasis and not visual noise.
    """
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    c = QColor(color)
    c.setAlpha(alpha)
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, 0)
    effect.setColor(c)
    widget.setGraphicsEffect(effect)


def vgradient(top: str, bottom: str) -> str:
    """A top-to-bottom QSS gradient stop pair - Qt Style Sheets support
    qlineargradient() directly, unlike box-shadow; used for the toolbar
    and sidebar masthead so they read as lit surfaces instead of flat
    fills, translating the reference's sheen/gradient-stripe technique
    into what QSS can actually express.
    """
    return f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bottom})"


# ------------------------------------------------------------------ toasts
# In-app toast notifications, stacked bottom-right over the main window.
# Sizing/timing modeled on a common toast pattern (accent-stripe card with a
# shrinking countdown bar); colors reuse the existing status palette above so
# a toast never introduces a color the rest of the app doesn't already use.
TOAST_WIDTH = 320
TOAST_MARGIN = 16      # gap from the window edge
TOAST_SPACING = 8      # gap between stacked toasts
# Toasts float over arbitrary app content, so their surface is a true
# opaque black rather than one of the translucent-looking elevation
# steps - a toast must never let whatever is behind it show through.
# Painted directly in _ToastCard.paintEvent (not via QSS): a QWidget
# *subclass* does not paint a stylesheet background at all unless
# WA_StyledBackground is set, which is what made these look transparent.
TOAST_BG = "#000000"
TOAST_STRIPE_WIDTH = 3
TOAST_DEFAULT_DURATION_MS = 4500
TOAST_SLIDE_MS = DURATION_SLOW
TOAST_KIND_COLORS = {
    "info": ACCENT,
    "success": SUCCESS,
    "warning": WARNING,
    "error": ERROR,
}

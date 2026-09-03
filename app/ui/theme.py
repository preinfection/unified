"""The design system's front door.

Everything in the app imports this module as `t` and reads tokens off it.
It is deliberately thin: the scales live in `app.ui.design.tokens`, the
color roles in `app.ui.design.palette`, and the active theme in
`app.ui.design.theme`. What this file adds is that *color* lookups resolve
against the palette that is active right now, through a module-level
`__getattr__`.

That matters for one specific reason: the app can switch between light and
dark while it is running. If `t.TEXT_PRIMARY` were an ordinary module
constant it would be frozen at import time, and every hand-painted surface
(the message-row delegate, the avatar, the navigation indicator) would go
on painting yesterday's theme until the process restarted. Because the
lookup is a function call, a delegate that reads `t.TEXT_PRIMARY` inside
`paint()` is simply correct on its next repaint, with no invalidation
protocol and nothing to remember to wire up.

Naming: the UPPER_CASE names below are the semantic roles spelled the way
Python constants are spelled. `BG_APP` is the message-list floor,
`BG_SIDEBAR` the navigation column, `BG_PANEL` the raised reading
surface - the same three-step elevation the palette defines, under the
names the codebase already uses for them.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont  # noqa: F401  (QFont re-exported)

from app.ui.design import palette as _palette_mod
from app.ui.design import tokens as _tokens
from app.ui.design.palette import Palette, contrast_ratio, mix, relative_luminance
from app.ui.design.theme import (
    MODE_DARK,
    MODE_LIGHT,
    MODE_SYSTEM,
    MODES,
    repolish,
    set_variant,
    theme_manager,
)
from app.ui.design.tokens import (  # noqa: F401  (re-exported scale tokens)
    AVATAR_LG,
    AVATAR_MD,
    AVATAR_SM,
    BODY_PADDING,
    BREAKPOINT_COLLAPSE_SIDEBAR,
    BREAKPOINT_STACK_READER,
    COMMAND_BAR_HEIGHT,
    CONTROL_LG,
    CONTROL_MD,
    CONTROL_SM,
    CONTROL_XS,
    DENSITY_COMPACT,
    DENSITY_COZY,
    DENSITY_DEFAULT,
    DENSITY_METRICS,
    DENSITY_ORDER,
    DENSITY_RELAXED,
    DURATION_BASE,
    DURATION_FAST,
    DURATION_INSTANT,
    DURATION_SLOW,
    FONT_FAMILIES,
    FONT_FAMILIES_CSS,
    FONT_FAMILIES_MONO,
    FONT_FAMILIES_MONO_CSS,
    GROUP_HEADER_HEIGHT,
    ICON_LG,
    ICON_MD,
    ICON_SM,
    ICON_XL,
    ICON_XS,
    LIST_HEADER_HEIGHT,
    LIST_WIDTH_DEFAULT,
    LIST_WIDTH_MIN,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_NONE,
    RADIUS_PILL,
    RADIUS_SCALE,
    RADIUS_SM,
    RADIUS_XL,
    RADIUS_XS,
    READER_HEADER_HEIGHT,
    READER_MAX_TEXT_WIDTH,
    READER_WIDTH_MIN,
    ROW_SPACING,
    SHADOW_PRESETS,
    SIDEBAR_RAIL_WIDTH,
    SIDEBAR_WIDTH,
    SIDEBAR_WIDTH_MIN,
    SIZE_2XL,
    SIZE_2XS,
    SIZE_3XL,
    SIZE_LG,
    SIZE_MD,
    SIZE_SM,
    SIZE_XL,
    SIZE_XS,
    SPACE_0,
    SPACE_2XL,
    SPACE_2XS,
    SPACE_3XL,
    SPACE_4XL,
    SPACE_5XL,
    SPACE_6XL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACING_SCALE,
    STATUS_BAR_HEIGHT,
    STROKE_FOCUS,
    STROKE_THICK,
    STROKE_THIN,
    TAB_HEIGHT,
    TITLE_HEIGHT,
    TYPOGRAPHY,
    WEIGHT_BOLD,
    WEIGHT_MEDIUM,
    WEIGHT_REGULAR,
    WEIGHT_SEMIBOLD,
    make_font,
)

__all__ = ["make_font", "qcolor", "theme_manager", "Palette"]

# --------------------------------------------------- legacy spacing names
# The pre-redesign scale used XXS/XXL/XXXL; the token module standardised
# on 2XS/2XL/etc. Both names point at the same numbers so no call site had
# to be touched purely for a rename.
SPACE_XXS = SPACE_2XS
SPACE_XXL = SPACE_4XL
SPACE_XXXL = SPACE_6XL
SIZE_TITLE = SIZE_2XL
SIZE_XXL = SIZE_2XL
ICON_SIZE_ROW = _tokens.ICON_XS + 1   # inline row glyph (star / attachment)
ICON_SIZE_ACTION = _tokens.ICON_MD    # reading-pane and compose actions
ICON_SIZE_TOOLBAR = _tokens.ICON_MD
ICON_SIZE_NAV = _tokens.ICON_MD

HEIGHT_SM = CONTROL_SM
HEIGHT_MD = CONTROL_MD
HEIGHT_LG = CONTROL_LG

# ------------------------------------------------------ live color roles
# name used in code -> palette role. Resolved on every attribute access
# (see __getattr__) so a running app can change theme.
_COLOR_ALIASES = {
    # Surfaces
    "BG_APP": "canvas",
    "BG_CANVAS": "canvas",
    "BG_SIDEBAR": "sidebar",
    "BG_PANEL": "surface",
    "BG_SURFACE": "surface",
    "BG_HOVER": "surface_hover",
    "BG_ACTIVE": "surface_active",
    "BG_SELECTED": "selected",
    "BG_SELECTED_INACTIVE": "selected_inactive",
    "BG_OVERLAY": "overlay",
    "SCRIM": "scrim",
    # Strokes
    "BORDER_SUBTLE": "border_subtle",
    "BORDER": "border",
    "BORDER_LIGHT": "border_strong",
    "BORDER_STRONG": "border_strong",
    "FOCUS_RING": "focus_ring",
    # Text
    "TEXT_PRIMARY": "text_primary",
    "TEXT_SECONDARY": "text_secondary",
    "TEXT_TERTIARY": "text_tertiary",
    "TEXT_DISABLED": "text_disabled",
    "TEXT_ON_ACCENT": "text_on_accent",
    "TEXT_LINK": "text_link",
    # Accent
    "ACCENT": "accent",
    "ACCENT_HOVER": "accent_hover",
    "ACCENT_PRESSED": "accent_pressed",
    "ACCENT_GLOW": "accent_hover",
    "ACCENT_SOFT_BG": "accent_subtle",
    "ACCENT_SUBTLE": "accent_subtle",
    "ACCENT_FG": "accent_fg",
    "ACCENT_SOLID": "accent_solid",
    "ACCENT_SOLID_HOVER": "accent_solid_hover",
    "ACCENT_SOLID_PRESSED": "accent_solid_pressed",
    # Status
    "INFO": "info_fg",
    "INFO_BG": "info_bg",
    "SUCCESS": "success_fg",
    "SUCCESS_BG": "success_bg",
    "WARNING": "warning_fg",
    "WARNING_BG": "warning_bg",
    "ERROR": "danger_fg",
    "ERROR_BG": "danger_bg",
    "DANGER_STRONG": "danger_strong",
    "SECURE": "success_fg",
    "STARRED": "star",
    "UNREAD": "unread",
    # Icon defaults
    "ICON_SECONDARY": "text_secondary",
    "ICON_ACTIVE": "text_primary",
    "ICON_SELECTED": "accent",
    "ICON_DISABLED": "text_disabled",
}

# Sync status -> the palette role its dot is painted with.
_STATUS_ROLES = {
    "syncing": "accent",
    "waiting": "text_tertiary",
    "done": "success_fg",
    "partial": "warning_fg",
    "error": "danger_fg",
    "idle": "text_tertiary",
}


def __getattr__(name: str) -> object:
    """Resolve color names against the palette that is active right now."""
    role = _COLOR_ALIASES.get(name)
    if role is not None:
        return theme_manager.palette.color(role)
    if name == "STATUS_COLORS":
        p = theme_manager.palette
        return {key: p.color(role) for key, role in _STATUS_ROLES.items()}
    if name == "AVATAR_HUES":
        return theme_manager.palette.avatar_hues
    if name == "PALETTE":
        return theme_manager.palette
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        list(globals()) + list(_COLOR_ALIASES) + ["STATUS_COLORS", "AVATAR_HUES", "PALETTE"]
    )


def qcolor(hex_value: str) -> QColor:
    return QColor(hex_value)


def status_color(status_key: str) -> str:
    return theme_manager.palette.color(_STATUS_ROLES.get(status_key, "text_tertiary"))


def is_dark() -> bool:
    return theme_manager.is_dark


def duration(base_ms: int) -> int:
    """Animation duration, honouring the OS reduced-motion preference."""
    return theme_manager.duration(base_ms)


def row_height() -> int:
    return theme_manager.row_height


def row_lines() -> int:
    return theme_manager.row_lines


# ------------------------------------------------------------- elevation


def apply_soft_shadow(widget, blur: int = 22, y_offset: int = 6,
                      alpha: int = 100) -> None:
    """Attach a real drop shadow to a surface that genuinely floats.

    Qt Style Sheets have no box-shadow, so this is the only way to express
    elevation beyond surface contrast. Used sparingly and never on a
    scrolling view: QGraphicsDropShadowEffect forces the whole subtree
    through a software raster path on every repaint.
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


# ------------------------------------------------------------------ toasts
# Toasts are the one deliberately inverted surface in the product: a black
# card in both themes, so a transient system message never reads as part
# of the mailbox behind it. Painted directly in _ToastCard.paintEvent
# (not via QSS) because a QWidget *subclass* does not paint a stylesheet
# background at all unless WA_StyledBackground is set.
TOAST_WIDTH = 320
TOAST_MARGIN = 16
TOAST_SPACING = 8
TOAST_BG = "#000000"
TOAST_STRIPE_WIDTH = 3
TOAST_DEFAULT_DURATION_MS = 4500
TOAST_SLIDE_MS = DURATION_SLOW


def toast_kind_colors() -> dict[str, str]:
    p = theme_manager.palette
    return {
        "info": p.accent,
        "success": p.success_fg,
        "warning": p.warning_fg,
        "error": p.danger_fg,
    }


# Kept as a module attribute for call sites that index it directly. The
# values are the *dark* palette's status hues, which is correct in both
# themes because the toast surface is black in both.
TOAST_KIND_COLORS = {
    "info": _palette_mod.DARK.accent,
    "success": _palette_mod.DARK.success_fg,
    "warning": _palette_mod.DARK.warning_fg,
    "error": _palette_mod.DARK.danger_fg,
}

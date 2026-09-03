"""Dimensional design tokens: the scales every surface in Unified measures
itself against.

Colors live next door in `palette.py` because they are the only tokens
that change with the active theme; everything here - spacing, radii, type,
motion, control geometry - is theme-independent and therefore a plain
constant.

Rules this file exists to enforce:

* No widget invents a pixel value. If a number appears in layout code and
  is not one of these tokens, that is a bug, not a style choice.
* The scales are short on purpose. A spacing ramp with twenty steps is the
  same as no ramp at all - the point is that a reader can tell "one step
  tighter" from "two steps tighter" at a glance.
* Shape is used deliberately, not uniformly. The radius ramp tops out at
  12px so a dialog still reads as a dialog and an inbox row still reads as
  a row, instead of everything melting into identical pills.
"""

from __future__ import annotations

from PySide6.QtGui import QFont

# --------------------------------------------------------------- spacing
# A 4px base with two half-steps (2, 6) for optical corrections inside
# small controls. Anything not on this ramp is a mistake.
SPACE_0 = 0
SPACE_2XS = 2
SPACE_XS = 4
SPACE_SM = 6
SPACE_MD = 8
SPACE_LG = 12
SPACE_XL = 16
SPACE_2XL = 20
SPACE_3XL = 24
SPACE_4XL = 32
SPACE_5XL = 40
SPACE_6XL = 48

SPACING_SCALE = (
    SPACE_0, SPACE_2XS, SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL,
    SPACE_2XL, SPACE_3XL, SPACE_4XL, SPACE_5XL, SPACE_6XL,
)

# ----------------------------------------------------------------- radii
# Deliberately restrained. Small controls are nearly square, cards are
# gently softened, only overlays and dialogs get the largest step, and
# RADIUS_PILL is reserved for things that genuinely are pills (count
# badges, the search field) - never for buttons or rows.
RADIUS_NONE = 0
RADIUS_XS = 4      # checkboxes, chips, menu items, indicator bars
RADIUS_SM = 6      # buttons, inputs, list rows, dropdown options
RADIUS_MD = 8      # navigation items, menus, toasts, panel bodies
RADIUS_LG = 10     # cards, grouped setting panels
RADIUS_XL = 12     # dialogs, popovers, the largest surfaces in the app
RADIUS_PILL = 999  # badges, the search field - things that truly are round

RADIUS_SCALE = (RADIUS_XS, RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL)

# --------------------------------------------------------------- strokes
STROKE_THIN = 1
STROKE_THICK = 2
STROKE_FOCUS = 2

# ------------------------------------------------------- control metrics
# Total control heights, derived from line height + padding + stroke.
# Unified/Qt-derived density choices, not values borrowed from a vendor spec.
CONTROL_XS = 22    # inline chips, list-row affordances
CONTROL_SM = 26    # compact toolbar actions, dense form controls
CONTROL_MD = 30    # the default: buttons, inputs, dropdowns
CONTROL_LG = 34    # primary actions (Compose, Send)

ICON_XS = 12
ICON_SM = 14
ICON_MD = 16
ICON_LG = 20
ICON_XL = 24

AVATAR_SM = 24
AVATAR_MD = 30
AVATAR_LG = 40

# --------------------------------------------------------- shell geometry
SIDEBAR_WIDTH = 248
SIDEBAR_WIDTH_MIN = 200
SIDEBAR_RAIL_WIDTH = 56      # collapsed sidebar (icons only)
LIST_WIDTH_MIN = 320
LIST_WIDTH_DEFAULT = 400
READER_WIDTH_MIN = 400
READER_MAX_TEXT_WIDTH = 760  # long-line guard for message bodies
COMMAND_BAR_HEIGHT = 48
LIST_HEADER_HEIGHT = 40
READER_HEADER_HEIGHT = 44
STATUS_BAR_HEIGHT = 26

# Window widths at which the shell changes shape. Real Qt constraints, not
# imported web breakpoints: each is the width below which the pane in
# question can no longer show its content without clipping.
BREAKPOINT_COLLAPSE_SIDEBAR = 920  # sidebar -> icon rail
BREAKPOINT_STACK_READER = 780      # reader takes over the list's space

# Legacy structural names kept so existing call sites keep describing the
# same things they always did.
TAB_HEIGHT = 30
BODY_PADDING = 12
ROW_SPACING = 2
TITLE_HEIGHT = 36

# ---------------------------------------------------------- list density
# The message list is the surface this product lives or dies on, so its
# density is a real user setting rather than one hard-coded number.
DENSITY_COMPACT = "compact"
DENSITY_COZY = "cozy"
DENSITY_RELAXED = "relaxed"
DENSITY_DEFAULT = DENSITY_COZY

# density -> (row height, lines of text shown per row)
DENSITY_METRICS = {
    DENSITY_COMPACT: (52, 2),
    DENSITY_COZY: (68, 3),
    DENSITY_RELAXED: (80, 3),
}
DENSITY_ORDER = (DENSITY_COMPACT, DENSITY_COZY, DENSITY_RELAXED)

GROUP_HEADER_HEIGHT = 28

# -------------------------------------------------------------- motion
# Four steps, each with a job. Anything longer than DURATION_SLOW is the UI
# making the user wait to watch an animation, which this app does not do.
# The single source is app/ui/design/motion.py, which also owns the easing
# curves; these names remain so existing call sites keep working.
DURATION_INSTANT = 90    # press feedback
DURATION_FAST = 130      # hover, focus rings, icon tints
DURATION_BASE = 190      # selection, indicator growth, content swaps
DURATION_SLOW = 260      # panels, dialogs, toasts entering or leaving

# ---------------------------------------------------------- typography
# A Windows-first system stack. QFont.setFamilies falls through the list,
# so no runtime OS check is needed; Segoe UI Variable is the Windows 11
# system face and Segoe UI covers Windows 10.
FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Arial", "sans-serif"]
FONT_FAMILIES_CSS = ", ".join(f'"{f}"' for f in FONT_FAMILIES[:-1]) + ", sans-serif"

# Windows ships Segoe UI Variable in three optical sizes, and they are not
# the same typeface at different scales: Text is drawn for small sizes with
# open apertures and loose spacing, Display is drawn for large sizes with
# tighter spacing and finer detail. Using Display above 17px is a real
# typographic decision that costs nothing and is native to the platform -
# unlike downloading whichever grotesk is currently fashionable.
FONT_FAMILIES_DISPLAY = [
    "Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI",
    "Arial", "sans-serif",
]
FONT_FAMILIES_DISPLAY_CSS = (
    ", ".join(f'"{f}"' for f in FONT_FAMILIES_DISPLAY[:-1]) + ", sans-serif"
)
# At and above this size a role is set in the Display optical cut.
DISPLAY_SIZE_THRESHOLD = 17
FONT_FAMILIES_MONO = ["Cascadia Mono", "Consolas", "Courier New", "monospace"]
FONT_FAMILIES_MONO_CSS = (
    ", ".join(f'"{f}"' for f in FONT_FAMILIES_MONO[:-1]) + ", monospace"
)

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_SEMIBOLD = 600
WEIGHT_BOLD = 700

# The size ramp. Every text style below resolves to one of these.
# The ramp. The previous one ran 11/12/13/14/16/19/24, where body (13) to
# subheading (14) is a ratio of 1.08 - a difference nobody can see, which
# is why the old hierarchy was carried by nothing. These steps widen once
# they leave the dense-metadata cluster: a subject line is now 22px
# against 13px body, a ratio of 1.7.
SIZE_2XS = 10
SIZE_XS = 11
SIZE_SM = 12
SIZE_MD = 13
SIZE_LG = 15
SIZE_XL = 18
SIZE_2XL = 22
SIZE_3XL = 28

# role -> (size, weight, letter-spacing px | None)
#
# Named for the job the text does, never for how big it is - so "what
# should a sender name look like" has exactly one answer, and changing that
# answer is a one-line edit here rather than a search across widgets.
TYPOGRAPHY: dict[str, tuple[int, int, float | None]] = {
    # Structural
    "display":          (SIZE_3XL, WEIGHT_SEMIBOLD, -0.5),
    "title":            (SIZE_2XL, WEIGHT_SEMIBOLD, -0.35),
    "heading":          (SIZE_XL, WEIGHT_SEMIBOLD, -0.2),
    "subheading":       (SIZE_LG, WEIGHT_SEMIBOLD, -0.1),
    "overline":         (SIZE_2XS, WEIGHT_BOLD, 0.9),
    # Body
    "body":             (SIZE_MD, WEIGHT_REGULAR, None),
    "body_strong":      (SIZE_MD, WEIGHT_SEMIBOLD, None),
    "body_sm":          (SIZE_SM, WEIGHT_REGULAR, None),
    "caption":          (SIZE_XS, WEIGHT_REGULAR, None),
    "caption_strong":   (SIZE_XS, WEIGHT_SEMIBOLD, None),
    # Controls
    "button":           (SIZE_MD, WEIGHT_SEMIBOLD, None),
    "button_sm":        (SIZE_SM, WEIGHT_SEMIBOLD, None),
    "nav_label":        (SIZE_MD, WEIGHT_MEDIUM, None),
    "nav_label_active": (SIZE_MD, WEIGHT_SEMIBOLD, None),
    "field_label":      (SIZE_SM, WEIGHT_MEDIUM, None),
    "field_value":      (SIZE_MD, WEIGHT_REGULAR, None),
    "menu_item":        (SIZE_MD, WEIGHT_REGULAR, None),
    "status":           (SIZE_SM, WEIGHT_MEDIUM, None),
    # Message list - the densest, most-read text in the product
    "sender":           (SIZE_MD, WEIGHT_SEMIBOLD, None),
    "sender_read":      (SIZE_MD, WEIGHT_REGULAR, None),
    "subject":          (SIZE_SM, WEIGHT_SEMIBOLD, None),
    "subject_read":     (SIZE_SM, WEIGHT_REGULAR, None),
    "preview":          (SIZE_SM, WEIGHT_REGULAR, None),
    "timestamp":        (SIZE_XS, WEIGHT_REGULAR, None),
    # Compatibility aliases for the pre-redesign role names.
    "app_title":        (SIZE_XL, WEIGHT_SEMIBOLD, -0.2),
    "dialog_heading":   (SIZE_XL, WEIGHT_SEMIBOLD, -0.2),
    "section_label":    (SIZE_2XS, WEIGHT_BOLD, 0.9),
    "account_label":    (SIZE_MD, WEIGHT_MEDIUM, None),
}


def make_font(preset: str, *, italic: bool = False, mono: bool = False) -> QFont:
    """Build a QFont for a named TYPOGRAPHY role."""
    size, weight, spacing = TYPOGRAPHY[preset]
    font = QFont()
    if mono:
        families = FONT_FAMILIES_MONO
    elif size >= DISPLAY_SIZE_THRESHOLD:
        families = FONT_FAMILIES_DISPLAY
    else:
        families = FONT_FAMILIES
    font.setFamilies(families)
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    if spacing is not None:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    font.setItalic(italic)
    return font


# ------------------------------------------------------------- elevation
# Qt Style Sheets have no box-shadow, so depth is either surface contrast
# (preferred, and free) or one QGraphicsDropShadowEffect - used only where
# a surface genuinely floats: menus, dialogs, toasts. Never on a scrolling
# view, where the effect forces a full repaint of the whole subtree.
SHADOW_PRESETS = {
    "sm": dict(blur=10, y_offset=2, alpha=60),
    "md": dict(blur=22, y_offset=6, alpha=100),
    "lg": dict(blur=38, y_offset=12, alpha=140),
}

"""Design system: every color, spacing, radius, typography, icon size,
control height, and animation duration the UI uses, in one place.

Single source of truth. style.py builds the QSS from these constants and
the custom-painted widgets (row delegate, avatars, nav items) import the
same values, so a hand-painted hover state can never drift from what the
stylesheet means by "hover", and no widget invents a one-off pixel value.

=========================================================================
HOW THIS FILE IS ORGANISED, AND WHY IT IS ORGANISED THAT WAY

Three layers, in this order. Nothing may skip a layer.

  1. RAMPS. Numbered, purely visual, no opinions: SURFACE_0..SURFACE_5 and
     the ink steps. Generated in OKLCH, never hand-picked.
  2. ALIASES. Semantic names bound to ramp steps: BG_APP, BG_HOVER,
     TEXT_PRIMARY. Widgets use these and never touch a ramp directly.
  3. STATE OVERLAYS. Translucent, not opaque: a hover is a wash laid OVER
     whatever surface it lands on, so one token is correct on the sidebar,
     on a list row and inside a menu without three separate values.

The old file had only layer 2, with every value hand-written. That is why
"hover" had to be redefined per surface and why two components could
disagree about it.

-------------------------------------------------------------------------
WHY THIS PALETTE

The values before this were translated 1:1 from OvertimeUI, a Roblox UI
library: bg(11,12,17), accent(96,165,255). Competently executed, and also
the single most predictable answer to "dark email client", arrived at by
copying a reference that had nothing to do with mail.

This palette is built from a scene instead: someone at a desk in the
evening, lamp on, working through a few hundred messages across accounts
they own, wanting the app to recede so the words are the only lit thing.
That forces dark, but WARM dark, the color of a room with a lamp in it
rather than a monitor in a server room.

TWO RULES CARRY THE WHOLE SYSTEM:

  1. NEUTRALS ARE WARM. Every surface and ink step is generated at OKLCH
     hue 70-88 with tiny chroma. Enough to read warm, far too little to
     read brown. No #000 and no #fff anywhere; both are dead next to a
     tinted ramp.

  2. COLOR IS A SIGNAL, NOT A SURFACE. Hue is reserved for things that
     mean something: sync state, an error, a starred message. Emphasis is
     carried by LUMINANCE, which is why ACCENT is warm bone in dark mode
     and near-black ink in light mode rather than a hue. The primary
     button is the brightest (or darkest) thing on screen, never the most
     saturated. A screen with nothing wrong on it is almost monochrome, so
     the one colored thing on it is unmissable.

-------------------------------------------------------------------------
EVERY VALUE IS MEASURED. Both ramps were generated in OKLCH and checked
for WCAG contrast against all four backgrounds text actually lands on, not
against one of them. tests/test_design_system.py re-checks this on every
run, in both modes, and fails the build rather than the design review.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# =========================================================================
# LAYER 1: RAMPS
# =========================================================================
# Numbered warm neutral steps, darkest to lightest in dark mode and the
# reverse in light. A widget never names one of these; they exist so that
# "one step up from the panel" is a real, checkable relationship instead of
# a second hand-picked hex.

_DARK = {
    # surface ramp, oklch hue 70, chroma 0.006-0.011
    "SURFACE_0": "#0c0a08",   # oklch(.145 .006 70)  window floor
    "SURFACE_1": "#13110e",   # oklch(.178 .007 70)  chrome
    "SURFACE_2": "#181512",   # oklch(.198 .008 70)  floating surfaces
    "SURFACE_3": "#1c1916",   # oklch(.216 .008 70)  inputs, controls
    "SURFACE_4": "#25211e",   # oklch(.252 .009 70)  hover
    "SURFACE_5": "#342f2a",   # oklch(.310 .011 72)  selected
    "LINE": "#2a2623",        # oklch(.272 .008 70)
    "LINE_STRONG": "#46423d",  # oklch(.380 .010 70)
    # ink, warming as it lightens so the brightest text is not blue-white
    "INK_1": "#efece7",       # oklch(.945 .008 84)
    "INK_2": "#a8a59e",       # oklch(.722 .010 80)
    "INK_3": "#8c8883",       # oklch(.630 .010 78)
    # emphasis: the top of the luminance ramp, not a hue
    "EMPHASIS": "#eee7d8",           # oklch(.930 .022 88)
    "EMPHASIS_HOVER": "#fbf6eb",     # oklch(.975 .016 88)
    "EMPHASIS_PRESSED": "#d4cbb9",   # oklch(.845 .026 86)
    "EMPHASIS_MUTED": "#928b7f",     # oklch(.640 .020 84)
    "ON_EMPHASIS": "#0c0a08",
    # the only real color in the app
    "SUCCESS": "#5ec386",     # oklch(.740 .130 155)
    "WARNING": "#ebb353",     # oklch(.800 .130  78)
    "ERROR": "#e86156",       # oklch(.660 .170  27)
    "STARRED": "#eabe4a",     # oklch(.820 .140  88)
    # translucent state washes, laid over whatever surface is beneath
    "WASH_HOVER": "rgba(255, 248, 235, 0.055)",
    "WASH_PRESSED": "rgba(0, 0, 0, 0.22)",
    "WASH_SELECTED": "rgba(255, 245, 225, 0.10)",
    "SCRIM": "rgba(6, 5, 4, 0.62)",
}

_LIGHT = {
    # warm paper, oklch hue 80-88
    "SURFACE_0": "#fbfaf7",   # oklch(.985 .004 88)  content floor
    "SURFACE_1": "#f5f3ef",   # oklch(.965 .006 86)  inputs, controls
    "SURFACE_2": "#fbfaf7",   # floating surfaces sit bright in light mode
    "SURFACE_3": "#eeebe5",   # oklch(.940 .008 84)  chrome
    "SURFACE_4": "#eeebe5",   # hover
    "SURFACE_5": "#e3dfd8",   # oklch(.905 .010 82)  selected
    "LINE": "#dcd9d2",        # oklch(.885 .010 82)
    "LINE_STRONG": "#bcb7ae",  # oklch(.780 .014 80)
    "INK_1": "#24201a",       # oklch(.245 .012 70)
    "INK_2": "#5b5650",       # oklch(.455 .012 72)
    "INK_3": "#656059",       # oklch(.490 .012 74)
    # in light mode emphasis is the DARK end of the same ramp: still
    # luminance, still not a hue, still the loudest thing on the screen.
    "EMPHASIS": "#392a1e",           # oklch(.300 .030 60)
    "EMPHASIS_HOVER": "#28190d",     # oklch(.230 .032 58)
    "EMPHASIS_PRESSED": "#1c0e05",   # oklch(.180 .030 56)
    "EMPHASIS_MUTED": "#918b83",     # oklch(.640 .014 76)
    "ON_EMPHASIS": "#fbfaf7",
    "SUCCESS": "#00753e",     # oklch(.490 .130 155)
    "WARNING": "#975800",     # oklch(.520 .130  70)
    "ERROR": "#b32322",       # oklch(.500 .180  27)
    "STARRED": "#895800",     # oklch(.500 .130  80)
    "WASH_HOVER": "rgba(40, 28, 16, 0.055)",
    "WASH_PRESSED": "rgba(40, 28, 16, 0.13)",
    "WASH_SELECTED": "rgba(40, 28, 16, 0.085)",
    "SCRIM": "rgba(36, 32, 26, 0.38)",
}

MODES = {"dark": _DARK, "light": _LIGHT}
MODE = "dark"

# ---- declared for readers and type checkers; apply_mode() owns the values.
SURFACE_0 = SURFACE_1 = SURFACE_2 = SURFACE_3 = SURFACE_4 = SURFACE_5 = ""
LINE = LINE_STRONG = ""
INK_1 = INK_2 = INK_3 = ""
EMPHASIS = EMPHASIS_HOVER = EMPHASIS_PRESSED = EMPHASIS_MUTED = ON_EMPHASIS = ""
SUCCESS = WARNING = ERROR = STARRED = ""
WASH_HOVER = WASH_PRESSED = WASH_SELECTED = SCRIM = ""

# =========================================================================
# LAYER 2: ALIASES
# =========================================================================
# What widgets actually name. Every one is bound to a ramp step above, so a
# palette change is a change in one table rather than a search across the
# codebase.
BG_APP = BG_SIDEBAR = BG_PANEL = BG_HOVER = BG_SELECTED = BG_OVERLAY = ""
BORDER = BORDER_LIGHT = ""
TEXT_PRIMARY = TEXT_SECONDARY = TEXT_TERTIARY = TEXT_ON_ACCENT = ""
ACCENT = ACCENT_HOVER = ACCENT_PRESSED = ACCENT_MUTED = ACCENT_SOFT_BG = ""
SECURE = DESTRUCTIVE = DESTRUCTIVE_HOVER = FOCUS_RING = ""
STATUS_COLORS: dict[str, str] = {}


def apply_mode(mode: str) -> None:
    """Rebind every color token to the named mode.

    WHY REBINDING GLOBALS RATHER THAN A THEME OBJECT: the custom painters
    in this app read `t.BG_SELECTED` at paint time, inside paintEvent. That
    is an attribute lookup on this module, so swapping the module's globals
    and triggering a repaint is all a theme switch needs on the painted
    side. The stylesheet side is not automatic: the caller must also
    re-apply style.get_stylesheet(), because QSS is a string Qt has already
    parsed. MainWindow.set_theme_mode() does both, in that order.
    """
    global MODE
    if mode not in MODES:
        raise ValueError(f"unknown theme mode {mode!r}")
    MODE = mode
    p = MODES[mode]
    g = globals()
    g.update(p)

    # ---- aliases -------------------------------------------------------
    g["BG_APP"] = p["SURFACE_0"]
    g["BG_SIDEBAR"] = p["SURFACE_3"] if mode == "light" else p["SURFACE_1"]
    g["BG_PANEL"] = p["SURFACE_1"] if mode == "light" else p["SURFACE_3"]
    g["BG_HOVER"] = p["SURFACE_4"]
    g["BG_SELECTED"] = p["SURFACE_5"]
    g["BG_OVERLAY"] = p["SURFACE_2"]
    g["BORDER"] = p["LINE"]
    g["BORDER_LIGHT"] = p["LINE_STRONG"]
    g["TEXT_PRIMARY"] = p["INK_1"]
    g["TEXT_SECONDARY"] = p["INK_2"]
    g["TEXT_TERTIARY"] = p["INK_3"]
    g["TEXT_ON_ACCENT"] = p["ON_EMPHASIS"]
    g["ACCENT"] = p["EMPHASIS"]
    g["ACCENT_HOVER"] = p["EMPHASIS_HOVER"]
    g["ACCENT_PRESSED"] = p["EMPHASIS_PRESSED"]
    g["ACCENT_MUTED"] = p["EMPHASIS_MUTED"]
    # Selection is a change in elevation, never a colored wash.
    g["ACCENT_SOFT_BG"] = p["SURFACE_5"]
    g["SECURE"] = p["SUCCESS"]
    # Destructive is the error hue and nothing else: an action that
    # destroys data must look like the thing that reports data loss.
    g["DESTRUCTIVE"] = p["ERROR"]
    g["DESTRUCTIVE_HOVER"] = mix(p["ERROR"], p["INK_1"], 0.22)
    # Focus is the emphasis value, so the focused thing is the brightest
    # (dark mode) or darkest (light mode) edge on screen. No blue ring.
    g["FOCUS_RING"] = p["EMPHASIS"]

    # "syncing" is deliberately not a fifth hue: it is progress, not a
    # verdict, and every place that shows it pairs the dot with a label.
    g["STATUS_COLORS"] = {
        "syncing": p["EMPHASIS"],
        "waiting": p["INK_3"],
        "done": p["SUCCESS"],
        "partial": p["WARNING"],
        "error": p["ERROR"],
        "idle": p["INK_3"],
    }

    # Toast surfaces follow the mode too, or a light-mode toast would be a
    # black slab.
    g["ICON_SECONDARY"] = p["INK_2"]
    g["ICON_ACTIVE"] = p["INK_1"]
    g["ICON_SELECTED"] = p["INK_1"]   # luminance, not hue
    g["ICON_DISABLED"] = p["INK_3"]

    g["TOAST_BG"] = p["SURFACE_2"]
    g["TOAST_BORDER"] = p["LINE_STRONG"]
    g["TOAST_KIND_COLORS"] = {
        "info": p["INK_2"],
        "success": p["SUCCESS"],
        "warning": p["WARNING"],
        "error": p["ERROR"],
    }


def mix(a: str, b: str, amount: float) -> str:
    """Blend two hex colors, `amount` 0..1 toward `b`.

    One implementation, so a hover tint computed in a delegate and one
    computed in a button land on the same value. Replaces the per-module
    _mix helpers that had started appearing in individual widgets.
    """
    amount = 0.0 if amount < 0 else 1.0 if amount > 1 else amount
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * amount),
        round(ca.green() + (cb.green() - ca.green()) * amount),
        round(ca.blue() + (cb.blue() - ca.blue()) * amount),
    ).name()


def role(widget, name: str):
    """Tag a widget with a text role instead of hard-coding its colour.

    USE THIS INSTEAD OF setStyleSheet("color: ..."). An inline stylesheet
    outranks the application stylesheet, so a colour written that way is
    frozen at construction and survives a theme change - which is exactly
    the bug that made the light palette unusable even once it was
    reachable. A role is a dynamic property, style.py has a rule per role,
    and Qt re-evaluates it every time the app stylesheet is re-applied.

    Roles: primary, secondary, tertiary, danger, warning, success,
    on-accent. Returns the widget so it can be used inline.
    """
    widget.setProperty("role", name)
    style = widget.style()
    if style is not None:
        # Qt does not re-evaluate a property selector on an already-polished
        # widget until it is told to. Harmless before the widget is shown.
        style.unpolish(widget)
        style.polish(widget)
    return widget


def retheme_tree(root) -> None:
    """Ask every widget under `root` that knows how to re-theme itself to
    do so.

    Text colour follows the stylesheet (see role()), but ICONS cannot: an
    icon is a pixmap rasterized and tinted with a specific colour at build
    time, so a widget holding one has to rebuild it when the palette moves.
    Rather than MainWindow keeping a list of which widgets those are - a
    list that is wrong the moment someone adds a widget - anything with a
    `retheme()` method opts itself in here.
    """
    from PySide6.QtWidgets import QWidget

    targets = [root, *root.findChildren(QWidget)]
    for widget in targets:
        fn = getattr(widget, "retheme", None)
        if callable(fn):
            try:
                fn()
            except Exception:  # one bad widget must not abort a theme switch
                import logging
                logging.getLogger(__name__).exception(
                    "retheme failed for %s", type(widget).__name__
                )


def qcolor(hex_value: str) -> QColor:
    """A QColor from a token. Accepts the rgba(...) wash tokens too, which
    QColor cannot parse on its own."""
    if hex_value.startswith("rgba"):
        parts = hex_value[hex_value.index("(") + 1:hex_value.rindex(")")].split(",")
        r, g, b = (int(float(x)) for x in parts[:3])
        a = float(parts[3]) if len(parts) > 3 else 1.0
        color = QColor(r, g, b)
        color.setAlphaF(a)
        return color
    return QColor(hex_value)


def is_dark() -> bool:
    return MODE == "dark"


# =========================================================================
# SPACING
# =========================================================================
# One 4px scale. Rhythm comes from choosing different steps for different
# relationships, not from one padding value used everywhere.
SPACE_XXS = 2
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXL = 32
SPACE_XXXL = 48

# =========================================================================
# RADII
# =========================================================================
# Deliberately tight. The old scale put 8-12px on every panel, which made a
# workspace out of identical rounded rectangles. Corners here read as
# precision rather than softness, and the largest is reserved for genuinely
# floating surfaces. Primer's own scale puts 3px on small controls and 6px
# on buttons; this sits in the same range on purpose.
#
# tests/test_design_system.py pins RADIUS_SM <= 6 and RADIUS_LG <= 12. That
# constraint is intentional. Do not raise it to make the UI rounder.
RADIUS_XS = 3     # checkboxes, badges, menu items
RADIUS_SM = 5     # inputs, buttons, list rows
RADIUS_MD = 7     # nav items, panel bodies
RADIUS_LG = 10    # floating surfaces
RADIUS_XL = 12    # dialogs, toasts
RADIUS_PILL = 999  # count badges only, never a search field

# =========================================================================
# BORDERS
# =========================================================================
BORDER_WIDTH = 1
FOCUS_WIDTH = 1

# =========================================================================
# CONTROL AND ROW SIZES
# =========================================================================
HEIGHT_SM = 26     # chips, inline actions
HEIGHT_MD = 32     # standard buttons and inputs
HEIGHT_LG = 38     # primary actions

TAB_HEIGHT = 34        # one nav item
BODY_PADDING = 16      # inner padding of a content page
ROW_SPACING = 2        # gap between stacked control rows
TITLE_HEIGHT = 36      # dialog header band
SIDEBAR_WIDTH = 248    # a real email address at 13px without eliding
# Tall enough for the dock (44) with 6px of band above and below it.
TOOLBAR_HEIGHT = 56

# Message list density. Three lines (sender + time, subject, snippet) is
# what real clients use and what makes a list scannable; the old single
# combined line meant subject and preview competed inside one string.
ROW_HEIGHT_COMFORTABLE = 76
ROW_HEIGHT_COMPACT = 56
ROW_GROUP_HEIGHT = 34

ICON_SIZE_ROW = 13     # inline row glyphs
ICON_SIZE_ACTION = 16  # reading pane and compose actions
ICON_SIZE_TOOLBAR = 18
ICON_SIZE_NAV = 17

# =========================================================================
# MOTION
# =========================================================================
# 150-250ms on most transitions, eased out, never bouncing. Users are in a
# task and must not wait on choreography. Nothing animates for decoration:
# every duration below is attached to a state change.
DURATION_FAST = 120   # hover and press feedback
DURATION_BASE = 180   # selection changes, content swaps
DURATION_SLOW = 280   # panels, dialogs
# The theme reveal: one circle crossing the whole window. It is the only
# transition that has to travel a full window's diagonal, and at 280ms that
# distance reads as a flash rather than as something opening. Magic UI's
# toggler uses 400ms for the same reason.
DURATION_THEME = 400


def ease_out():
    """The app's single easing curve.

    One curve everywhere, so two animated components never feel like they
    come from different products. Exponential ease-out: fast departure,
    long settle, no overshoot.
    """
    from PySide6.QtCore import QEasingCurve

    return QEasingCurve.Type.OutQuint


# =========================================================================
# TYPOGRAPHY
# =========================================================================
# A native Windows 11 stack. Segoe UI Variable is the modern system font;
# QFont.setFamilies falls back through the list automatically, so this
# needs no runtime OS check.
#
# One family carries headings, labels, buttons and body. Product UI does
# not need a display/body pairing, and a display face in a control label is
# a reliable mark of a UI designed by someone enjoying themselves.
FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Arial", "sans-serif"]
FONT_FAMILIES_CSS = ", ".join(f'"{f}"' for f in FONT_FAMILIES[:-1]) + ", sans-serif"

# Metadata read as data rather than prose (timestamps, sizes, counts) is
# set in the system mono face. It aligns in a column, it stops a date
# looking like a word, and it is the one typographic signal that says
# "this is a value".
FONT_MONO = ["Cascadia Mono", "Consolas", "Courier New", "monospace"]
FONT_MONO_CSS = ", ".join(f'"{f}"' for f in FONT_MONO[:-1]) + ", monospace"

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_SEMIBOLD = 600
WEIGHT_BOLD = 700

# ~1.2 between the steps that carry hierarchy, which is the product range;
# exaggerated contrast is noise in an interface with this many text
# elements. The old scale ran 11/12/13/14/16/20/22, where the four smallest
# were within 8% of each other and did no work at all.
SIZE_XS = 11    # captions, counters
SIZE_SM = 12    # metadata, secondary labels
SIZE_MD = 13    # the UI default
SIZE_LG = 14    # body, sender names
SIZE_XL = 17    # section headings
SIZE_XXL = 20   # dialog headings
SIZE_TITLE = 24  # the largest thing in the app

# The reading pane is a page, not a row: its own size, leading and measure,
# because it is the surface people spend minutes on and the one place this
# app should be plainly better than a webmail tab.
SIZE_READING = 15
READING_LINE_HEIGHT = 165  # percent
READING_MEASURE_CH = 72    # 65-75 rule

TYPOGRAPHY: dict[str, tuple[int, int, float | None]] = {
    "app_title": (SIZE_TITLE, WEIGHT_SEMIBOLD, -0.3),
    "dialog_heading": (SIZE_XXL, WEIGHT_SEMIBOLD, -0.2),
    "section_heading": (SIZE_XL, WEIGHT_SEMIBOLD, -0.1),
    "nav_label": (SIZE_MD, WEIGHT_MEDIUM, None),
    "section_label": (SIZE_XS, WEIGHT_SEMIBOLD, 1.1),
    "account_label": (SIZE_MD, WEIGHT_MEDIUM, None),
    "sender": (SIZE_LG, WEIGHT_SEMIBOLD, None),
    "sender_read": (SIZE_LG, WEIGHT_REGULAR, None),
    "subject": (SIZE_MD, WEIGHT_MEDIUM, None),
    "subject_read": (SIZE_MD, WEIGHT_REGULAR, None),
    "preview": (SIZE_SM, WEIGHT_REGULAR, None),
    "timestamp": (SIZE_XS, WEIGHT_REGULAR, None),
    "button": (SIZE_MD, WEIGHT_MEDIUM, None),
    "menu_item": (SIZE_MD, WEIGHT_REGULAR, None),
    "field_label": (SIZE_SM, WEIGHT_MEDIUM, None),
    "field_value": (SIZE_MD, WEIGHT_REGULAR, None),
    "body": (SIZE_LG, WEIGHT_REGULAR, None),
    "reading": (SIZE_READING, WEIGHT_REGULAR, None),
    "status": (SIZE_SM, WEIGHT_MEDIUM, None),
    "caption": (SIZE_XS, WEIGHT_REGULAR, None),
    "badge": (SIZE_XS, WEIGHT_SEMIBOLD, None),
}

# Presets rendered in the mono face: values, not prose.
MONO_PRESETS = frozenset({"timestamp", "badge"})


def make_font(preset: str, *, italic: bool = False) -> QFont:
    """Build a QFont from a named TYPOGRAPHY entry.

    NOTE FOR ANYONE EDITING style.py: a Qt stylesheet font overrides
    QWidget.setFont(), so a universal `* { font-size: ... }` rule silently
    flattens every call to this function. That bug shipped for two
    releases; app/main.py now sets the default font on QApplication instead
    and there is a test that fails if the rule comes back.
    """
    size, weight, spacing = TYPOGRAPHY[preset]
    font = QFont()
    mono = preset in MONO_PRESETS
    font.setFamilies(FONT_MONO if mono else FONT_FAMILIES)
    # The style hint is stated, not inherited. A QPainter resolves an
    # unset hint from the device it paints on, so a sans preset drawn onto
    # a monospace surface (the console's empty state) came out in whatever
    # monospace face the fallback found.
    font.setStyleHint(QFont.StyleHint.Monospace if mono else QFont.StyleHint.SansSerif)
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    if spacing is not None:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    font.setItalic(italic)
    return font


# =========================================================================
# ICONS
# =========================================================================
# Tints for Qt's four icon modes. Rebound by apply_mode() with everything
# else, because an icon color that did not follow the theme would be the
# one thing still dark on a light window.
ICON_SECONDARY = ICON_ACTIVE = ICON_SELECTED = ICON_DISABLED = ""


# =========================================================================
# ELEVATION
# =========================================================================
# Qt Style Sheets have no box-shadow, so real elevation is a
# QGraphicsDropShadowEffect. Pulled back hard from the previous values: on
# a near-black ground a heavy shadow reads as a smudge, not as height. What
# separates these surfaces is the ramp and a hairline; the shadow only
# confirms it, and only genuinely floating things get one at all.
SHADOW_PRESETS = {
    "sm": dict(blur=10, y_offset=2, alpha=60),
    "md": dict(blur=20, y_offset=5, alpha=95),
    "lg": dict(blur=34, y_offset=10, alpha=130),
}


def apply_soft_shadow(widget, blur: int = 20, y_offset: int = 5,
                      alpha: int = 95) -> None:
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    # A light theme needs a far softer shadow than a dark one, or every
    # floating surface looks like it is hovering a foot off the page.
    effect.setColor(QColor(0, 0, 0, alpha if is_dark() else int(alpha * 0.45)))
    widget.setGraphicsEffect(effect)


def apply_elevation(widget, level: str = "md") -> None:
    apply_soft_shadow(widget, **SHADOW_PRESETS[level])


# =========================================================================
# TOASTS
# =========================================================================
# NO ACCENT STRIPE. A toast used to carry a 3px colored bar down its left
# edge. A colored side-stripe is decoration standing in for meaning, and it
# put the only hue on the card where it was least likely to be read. The
# kind is a leading dot beside the title instead: a shape as well as a hue,
# so it survives color blindness and a glance from the corner of the eye.
TOAST_WIDTH = 340
TOAST_MARGIN = 16
TOAST_SPACING = 8
TOAST_ICON_SIZE = 16
TOAST_DEFAULT_DURATION_MS = 4500
TOAST_SLIDE_MS = DURATION_SLOW
TOAST_BG = ""
TOAST_BORDER = ""
TOAST_KIND_COLORS: dict[str, str] = {}


apply_mode("dark")

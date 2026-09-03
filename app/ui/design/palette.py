"""Semantic color roles, and the two palettes that fill them.

The whole app talks about color in terms of *what a color is for*
(`surface`, `text_secondary`, `accent_pressed`, `danger_fg`) and never in
terms of what it looks like. That is the difference between a design
system and a pile of hex codes: adding a light theme becomes filling in a
second column here rather than auditing forty widgets.

Two rules make this hold:

* A role is defined by its job and its pairing. `text_on_accent` is only
  ever drawn on `accent`; `danger_fg` is only ever drawn on `surface` or
  `danger_bg`. The contrast tests in tests/test_design_system.py assert
  exactly those pairings, in both themes.
* Interaction variants (`_hover`, `_pressed`, `_selected`) are derived
  from their base with `mix()` where a mechanical relationship is right,
  and hand-tuned where it isn't. Deriving them means dark and light can
  never drift apart by one being updated and the other forgotten.

Elevation runs *outward from the navigation*, not simply "darker is
lower": the sidebar is the most recessed surface, the message list sits
above it, and the reading pane is the brightest surface in the window.
That gradient is what tells a first-time user, without a single label,
which pane is chrome and which pane is content.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# --------------------------------------------------------------- helpers


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def mix(color_a: str, color_b: str, fraction: float) -> str:
    """Blend two hex colors. fraction=0 -> color_a, 1 -> color_b."""
    fraction = max(0.0, min(1.0, fraction))
    a, b = _rgb(color_a), _rgb(color_b)
    return "#%02x%02x%02x" % tuple(
        round(a[i] + (b[i] - a[i]) * fraction) for i in range(3)
    )


def relative_luminance(color: str) -> float:
    """WCAG 2.1 relative luminance."""
    channels = []
    for raw in _rgb(color):
        c = raw / 255.0
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.1 contrast ratio between two opaque colors (1.0 - 21.0)."""
    la, lb = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


# ------------------------------------------------------------ role table


@dataclass(frozen=True)
class Palette:
    """Every color role in the product. Adding a role here means adding it
    to both themes below - which is the point."""

    name: str
    is_dark: bool

    # Surfaces, from most recessed (navigation chrome) to most raised
    # (floating overlays).
    sidebar: str          # navigation column
    canvas: str           # message list / working area floor
    surface: str          # reading pane, panels, inputs, cards
    surface_hover: str    # a surface under the pointer
    surface_active: str   # a surface being pressed
    overlay: str          # menus, popovers, dialogs, toasts
    scrim: str            # the dim behind a modal

    # Selection
    selected: str         # selected row / active navigation fill
    selected_inactive: str  # same row when the view has lost focus

    # Strokes
    border_subtle: str    # separators inside a grouped surface
    border: str           # the default hairline between surfaces
    border_strong: str    # a control that wants a visible edge
    focus_ring: str       # keyboard focus - never removed, never subtle

    # Text
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_disabled: str
    text_on_accent: str
    text_link: str

    # Accent / brand
    # Accent has two families, and conflating them is how "blue button
    # with unreadable white label" happens:
    #   accent*      - the *hue*: indicators, focus, selected-row tints,
    #                  icon highlights. Never carries text on top of it.
    #   accent_solid* - a filled control that carries `text_on_accent`,
    #                  and is therefore tuned for 4.5:1 against white.
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_subtle: str    # tinted background behind an accented row
    accent_fg: str        # accent-colored text, legible on surface/subtle
    accent_solid: str
    accent_solid_hover: str
    accent_solid_pressed: str

    # Status. Each has a foreground (text/icon) and a subtle background.
    info_fg: str
    info_bg: str
    success_fg: str
    success_bg: str
    warning_fg: str
    warning_bg: str
    danger_fg: str
    danger_bg: str
    danger_strong: str    # a destructive *button* fill, not a tint

    # Domain-specific
    star: str             # the one non-semantic hue in the product
    unread: str           # unread indicator dot / count badge

    # Avatar hues - a small, deliberately desaturated set. Not a rainbow:
    # enough to tell correspondents apart, never enough to turn the inbox
    # into confetti.
    avatar_hues: tuple[str, ...]

    def role_names(self) -> tuple[str, ...]:
        return tuple(
            f.name for f in fields(self)
            if f.name not in ("name", "is_dark", "avatar_hues")
        )

    def color(self, role: str) -> str:
        return getattr(self, role)


# ----------------------------------------------------------------- dark
#
# A neutral graphite, not a blue-black: a strongly tinted dark theme reads
# as a "skin" rather than as a product, and it fights every message body
# rendered next to it. The three main surfaces are two full steps apart so
# the pane structure is legible at a glance even with all borders removed.

_D_ACCENT = "#4c8dff"

DARK = Palette(
    name="dark",
    is_dark=True,

    sidebar="#0b0c0e",
    canvas="#121317",
    surface="#17181d",
    surface_hover="#1e2026",
    surface_active="#24262e",
    overlay="#1b1d22",
    scrim="rgba(0, 0, 0, 140)",

    selected="#1b2635",
    selected_inactive="#1a1c22",

    border_subtle="#1f2127",
    border="#2a2d35",
    border_strong="#3b3f4a",
    focus_ring="#78aaff",

    text_primary="#e8eaee",
    text_secondary="#a0a5b0",
    text_tertiary="#7d838e",
    text_disabled="#565b64",
    text_on_accent="#ffffff",
    text_link="#7fb0ff",

    accent=_D_ACCENT,
    accent_hover="#6ba0ff",
    accent_pressed="#3a73d9",
    accent_subtle="#16233a",
    accent_fg="#85b4ff",
    accent_solid="#2569db",
    accent_solid_hover="#2f74e6",
    accent_solid_pressed="#1c56b8",

    info_fg="#7fb0ff",
    info_bg="#16233a",
    success_fg="#3fb950",
    success_bg="#122117",
    warning_fg="#d8a531",
    warning_bg="#241d0f",
    danger_fg="#f85149",
    danger_bg="#2a1416",
    danger_strong="#c93c34",

    star="#e3b341",
    unread=_D_ACCENT,

    avatar_hues=(
        "#5b8def", "#4fa8a0", "#8b7ce0", "#c9834f",
        "#5aa96f", "#c07b9d", "#4f93c4", "#a3894a",
    ),
)

# ---------------------------------------------------------------- light
#
# Not "the dark theme inverted". Light UI needs *more* structure from
# borders and less from fills, so the border roles carry more weight here
# and the surface steps are closer together - a light theme with dark
# theme contrast between panes looks like a bug report screenshot.

_L_ACCENT = "#1a6fe0"

LIGHT = Palette(
    name="light",
    is_dark=False,

    sidebar="#f1f2f4",
    canvas="#f7f8fa",
    surface="#ffffff",
    surface_hover="#eceef1",
    surface_active="#e3e6ea",
    overlay="#ffffff",
    scrim="rgba(16, 18, 22, 90)",

    selected="#e6f0fd",
    selected_inactive="#eef0f3",

    border_subtle="#eceef1",
    border="#dcdfe4",
    border_strong="#b9bec7",
    focus_ring="#1a6fe0",

    text_primary="#16181d",
    text_secondary="#565c66",
    text_tertiary="#666c75",
    text_disabled="#a2a8b2",
    text_on_accent="#ffffff",
    text_link="#0f5ec4",

    accent=_L_ACCENT,
    accent_hover="#1560c4",
    accent_pressed="#0f4c9c",
    accent_subtle="#eaf2fe",
    accent_fg="#0f5ec4",
    accent_solid=_L_ACCENT,
    accent_solid_hover="#1560c4",
    accent_solid_pressed="#0f4c9c",

    info_fg="#0f5ec4",
    info_bg="#eaf2fe",
    success_fg="#1a7f37",
    success_bg="#e8f5ec",
    warning_fg="#7d5800",
    warning_bg="#fdf3dc",
    danger_fg="#cf222e",
    danger_bg="#fdeced",
    danger_strong="#cf222e",

    star="#8a6400",
    unread=_L_ACCENT,

    avatar_hues=(
        "#3a6fc4", "#2d7a72", "#6a4fd0", "#a06333",
        "#3a7a55", "#a8497c", "#356e91", "#7a6633",
    ),
)

PALETTES = {DARK.name: DARK, LIGHT.name: LIGHT}

# The pairings the app actually renders, asserted by the contrast tests.
# (foreground role, background role, minimum ratio). 4.5 is WCAG AA for
# body text; 3.0 applies to large/bold text and to text drawn on a
# transient interaction surface (hover/pressed), which a reader is never
# asked to read at rest.
CONTRAST_CONTRACT: tuple[tuple[str, str, float], ...] = (
    ("text_primary", "sidebar", 4.5),
    ("text_primary", "canvas", 4.5),
    ("text_primary", "surface", 4.5),
    ("text_primary", "overlay", 4.5),
    ("text_primary", "selected", 4.5),
    ("text_secondary", "sidebar", 4.5),
    ("text_secondary", "canvas", 4.5),
    ("text_secondary", "surface", 4.5),
    ("text_secondary", "overlay", 4.5),
    ("text_tertiary", "sidebar", 4.5),
    ("text_tertiary", "canvas", 4.5),
    ("text_tertiary", "surface", 4.5),
    ("text_primary", "surface_hover", 3.0),
    ("text_secondary", "surface_hover", 3.0),
    ("text_tertiary", "surface_hover", 3.0),
    ("text_on_accent", "accent_solid", 4.5),
    ("text_on_accent", "accent_solid_hover", 4.0),
    ("text_on_accent", "accent_solid_pressed", 4.5),
    ("accent", "surface", 3.0),
    ("accent", "canvas", 3.0),
    ("accent_fg", "surface", 4.5),
    ("accent_fg", "canvas", 4.5),
    ("accent_fg", "accent_subtle", 4.5),
    ("accent_fg", "selected", 4.5),
    ("text_link", "surface", 4.5),
    ("info_fg", "info_bg", 4.5),
    ("success_fg", "success_bg", 4.5),
    ("warning_fg", "warning_bg", 4.5),
    ("danger_fg", "danger_bg", 4.5),
    ("danger_fg", "surface", 4.5),
    ("text_on_accent", "danger_strong", 4.5),
    ("star", "surface", 3.0),
    ("star", "canvas", 3.0),
    ("focus_ring", "surface", 3.0),
    ("focus_ring", "canvas", 3.0),
    ("focus_ring", "sidebar", 3.0),
)

# The pane elevation gradient: navigation is the most recessed surface and
# the reading pane the most raised, in *both* themes. "Distinct" is
# measured in luminance, not by comparing hex strings - two different hex
# values that render identically are still one surface.
ELEVATION_ORDER = ("sidebar", "canvas", "surface")

# Interaction surfaces move away from `surface` in a consistent direction:
# lighter in dark mode, darker in light mode. A light theme that lightens
# on hover has nowhere to go from white, which is why this is not simply
# an extension of ELEVATION_ORDER.
INTERACTION_ORDER = ("surface", "surface_hover", "surface_active")

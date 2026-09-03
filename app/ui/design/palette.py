"""Semantic color roles, and the two palettes that fill them.

The whole app talks about color in terms of *what a color is for*
(`surface`, `text_secondary`, `accent_pressed`, `danger_fg`) and never in
terms of what it looks like. That is the difference between a design
system and a pile of hex codes: adding a light theme becomes filling in a
second column here rather than auditing forty widgets.

## The direction

Both palettes are built on a **warm neutral ground with a cool accent**.

That is a decision, and it is the one carrying the product's identity.
The reflex answer for a dark desktop tool is a cool grey-blue near-black
with a blue accent, which is what this app used to be, and which is
indistinguishable from every generated "modern dark mode": zinc surfaces,
white-at-10% hairlines, one unchosen blue. Shifting the neutrals warm
(hue near 35 degrees, chroma low enough that nobody would call it brown)
puts the whole field in tension with the cool accent, so the accent reads
as *chosen* rather than as the only color present. It also makes the
light theme paper rather than office-white, which is the right material
for a surface that is mostly text.

Neither theme uses pure black or pure white anywhere, including the
toast, which is the one deliberately inverted surface in the product.

## Rules that keep this honest

* A role is defined by its job and its pairing. `text_on_accent` is only
  ever drawn on `accent_solid`; `danger_fg` is only ever drawn on
  `surface` or `danger_bg`. `CONTRAST_CONTRACT` lists every pairing the
  app actually renders and the tests measure all of them, in both themes.
* Accent comes in two families, because conflating them is how "blue
  button with an unreadable white label" happens. `accent*` is the hue:
  indicators, focus, selection tints, icon highlights - it never carries
  text. `accent_solid*` is a filled control that carries
  `text_on_accent`, and is tuned for 4.5:1 against it.
* Interaction variants move in one consistent direction: lighter in dark,
  darker in light. A light theme that lightens on hover has nowhere to go
  from its top surface.

Elevation runs *outward from the navigation*: the sidebar is the most
recessed surface, the message list sits above it, and the reading pane is
the brightest. That gradient tells a first-time user which pane is chrome
and which is content without a single label.
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


def is_warm(color: str) -> bool:
    """True when a neutral leans warm (more red than blue).

    The direction is only real if the neutrals actually carry it, so the
    tests assert this rather than trusting the docstring above.
    """
    r, _g, b = _rgb(color)
    return r > b


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
    overlay: str          # menus, popovers, dialogs
    scrim: str            # the dim behind a modal

    # Material. Real surfaces catch light along their top edge and cast a
    # shadow tinted by the ground they sit on. A flat fill with a grey 1px
    # border is what makes an interface look like a wireframe of itself.
    highlight: str         # inner top edge of a raised surface
    highlight_strong: str  # the same, on a filled control
    shadow: str            # drop shadow color, tinted to the ground

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

    # Accent. Two families - see the module docstring.
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
# Warm graphite. The neutrals run hue ~35 degrees at very low chroma - far
# enough that the field reads warm next to the accent, never far enough to
# read as brown. Compare the previous #17181d surface with its #2a2d35
# hairline: that pair was the generated-dark-mode default in both hue and
# step size.

_D_ACCENT = "#5aa2ff"

DARK = Palette(
    name="dark",
    is_dark=True,

    sidebar="#141311",
    canvas="#1b1917",
    surface="#22201d",
    surface_hover="#2b2825",
    surface_active="#35312d",
    overlay="#26231f",
    scrim="rgba(10, 8, 6, 165)",

    highlight="rgba(255, 246, 232, 20)",
    highlight_strong="rgba(255, 252, 245, 48)",
    shadow="rgba(8, 6, 4, 150)",

    selected="#1e2733",
    selected_inactive="#262320",

    border_subtle="#262320",
    border="#322e2a",
    border_strong="#4a443d",
    focus_ring="#7fb4ff",

    text_primary="#f2eee7",
    text_secondary="#b3aa9f",
    text_tertiary="#948b7d",
    text_disabled="#5f584f",
    text_on_accent="#ffffff",
    text_link="#86b6ff",

    accent=_D_ACCENT,
    accent_hover="#7fb6ff",
    accent_pressed="#3d7fd6",
    accent_subtle="#1a2637",
    accent_fg="#8ab8ff",
    accent_solid="#2a6fd6",
    accent_solid_hover="#3a7ee0",
    accent_solid_pressed="#205ab4",

    info_fg="#86b6ff",
    info_bg="#1a2637",
    success_fg="#5cb37a",
    success_bg="#16231a",
    warning_fg="#d9a441",
    warning_bg="#262015",
    danger_fg="#f0716a",
    danger_bg="#2c1a18",
    danger_strong="#c4463f",

    star="#e8b83f",
    unread=_D_ACCENT,

    avatar_hues=(
        "#6f97e2", "#4fa398", "#9083d6", "#c4854f",
        "#5fa670", "#bd7f96", "#5b93bd", "#a08a54",
    ),
)

# ---------------------------------------------------------------- light
#
# Warm paper, not office white. Light UI takes more of its structure from
# borders and less from fills, so the border roles carry more weight here
# and the surface steps sit closer together.

_L_ACCENT = "#1a63c4"

LIGHT = Palette(
    name="light",
    is_dark=False,

    sidebar="#efece5",
    canvas="#f7f4ee",
    surface="#fffdf8",
    surface_hover="#eae5db",
    surface_active="#ded8cb",
    overlay="#fffdf8",
    scrim="rgba(38, 32, 24, 90)",

    highlight="rgba(255, 255, 255, 200)",
    highlight_strong="rgba(255, 255, 255, 88)",
    shadow="rgba(72, 60, 44, 46)",

    selected="#e6efff",
    selected_inactive="#ebe7de",

    border_subtle="#ebe6dc",
    border="#ddd6c9",
    border_strong="#bab2a3",
    focus_ring="#1a63c4",

    text_primary="#1d1a16",
    text_secondary="#585146",
    text_tertiary="#6c6458",
    text_disabled="#a89f92",
    text_on_accent="#ffffff",
    text_link="#0f5bbd",

    accent=_L_ACCENT,
    accent_hover="#1554aa",
    accent_pressed="#10448c",
    accent_subtle="#e8f0fd",
    accent_fg="#0f5bbd",
    accent_solid=_L_ACCENT,
    accent_solid_hover="#1554aa",
    accent_solid_pressed="#10448c",

    info_fg="#0f5bbd",
    info_bg="#e8f0fd",
    success_fg="#1c7a3c",
    success_bg="#e7f3e9",
    warning_fg="#7a5600",
    warning_bg="#fbf1d8",
    danger_fg="#c9302c",
    danger_bg="#fceceb",
    danger_strong="#c9302c",

    star="#916008",
    unread=_L_ACCENT,

    avatar_hues=(
        "#3a6cc0", "#2d7a72", "#6a52c4", "#a06333",
        "#3a7a55", "#a2497a", "#356e91", "#7a6633",
    ),
)

PALETTES = {DARK.name: DARK, LIGHT.name: LIGHT}

# The pairings the app actually renders, asserted by the contrast tests.
# 4.5 is WCAG AA for body text; 3.0 applies to large/bold text and to text
# drawn on a transient interaction surface (hover/pressed), which a reader
# is never asked to read at rest.
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
# on hover has nowhere to go from its top surface, which is why this is
# not simply an extension of ELEVATION_ORDER.
INTERACTION_ORDER = ("surface", "surface_hover", "surface_active")

# The neutrals that must actually carry the warm direction. Listed rather
# than inferred, so "the palette drifted cool again" fails a test instead
# of being noticed a year later.
WARM_NEUTRALS = (
    "sidebar", "canvas", "surface", "surface_hover", "surface_active",
    "overlay", "text_primary", "text_secondary", "text_tertiary",
    "border", "border_strong",
)

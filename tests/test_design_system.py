"""Regression tests that the UI actually follows one shared design system.

These assert against measured properties and rendered pixels, not against
the presence of stylesheet text, so a component that quietly stops using
the shared tokens fails here.

REWRITTEN FOR THE WARM-ARCHIVE PALETTE. The previous version of this file
pinned every value to OvertimeUI, a Roblox UI library the palette had been
translated from: it asserted bg == (11,12,17) and accent == (96,165,255)
and that the nav pill painted a 3px accent bar on its left edge. Those are
all deliberately gone. What is guarded now is not a set of borrowed
numbers, it is the four rules the system is actually built on:

  1. neutrals are warm, and nothing is pure black or white
  2. every text step clears WCAG AA on every surface it lands on
  3. hue is reserved for meaning; emphasis is luminance
  4. no state is signalled by a colored bar on an element's edge

Plus one test for a bug that made the whole scale inert for two releases:
a stylesheet font-size silently overrode every setFont() in the app.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QLabel

from app.ui import motion, theme as t


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet
    # Mirrors app/main.py: the default font is set on the application, and
    # the stylesheet must not contain a rule that overrides it.
    app.setFont(t.make_font("field_value"))
    app.setStyleSheet(get_stylesheet())
    yield app


# ------------------------------------------------------------------ helpers

def _relative_luminance(hex_value: str) -> float:
    color = QColor(hex_value)

    def channel(v: float) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return (0.2126 * channel(color.red())
            + 0.7152 * channel(color.green())
            + 0.0722 * channel(color.blue()))


def contrast(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


SURFACES = {
    "app floor": t.BG_APP,
    "panel": t.BG_PANEL,
    "sidebar": t.BG_SIDEBAR,
    "hovered row": t.BG_HOVER,
}


def _swatches() -> dict[str, str]:
    return {
        name: value for name, value in vars(t).items()
        if isinstance(value, str) and value.startswith("#") and len(value) == 7
    }


# --------------------------------------------- 1. warm, and never absolute

def test_no_pure_black_or_white_anywhere_in_the_palette():
    """#000 and #fff are lifeless next to a tinted ramp, and one of them
    was in here: TOAST_BG used to be literal #000000."""
    swatches = _swatches()
    assert swatches, "no color tokens found - did the module move?"
    for name, value in swatches.items():
        assert value.lower() not in ("#000000", "#ffffff"), f"{name} is absolute"


def test_every_neutral_is_warm_tinted():
    """Warm means the red channel is at or above the blue one. The previous
    palette was the opposite on every step (blue-black), and this is the
    single change that stops the app reading as generic dark mode."""
    neutrals = [
        ("BG_APP", t.BG_APP), ("BG_SIDEBAR", t.BG_SIDEBAR),
        ("BG_PANEL", t.BG_PANEL), ("BG_HOVER", t.BG_HOVER),
        ("BG_SELECTED", t.BG_SELECTED), ("BG_OVERLAY", t.BG_OVERLAY),
        ("BORDER", t.BORDER), ("BORDER_LIGHT", t.BORDER_LIGHT),
        ("TEXT_PRIMARY", t.TEXT_PRIMARY), ("TEXT_SECONDARY", t.TEXT_SECONDARY),
        ("TEXT_TERTIARY", t.TEXT_TERTIARY), ("ACCENT", t.ACCENT),
    ]
    for name, value in neutrals:
        c = QColor(value)
        assert c.red() >= c.blue(), f"{name} ({value}) is cool, not warm"


def test_neutrals_stay_neutral():
    """Warm, but only just. A tint wide enough to name as a color has
    stopped being a neutral and started being brown."""
    for name, value in (("BG_APP", t.BG_APP), ("BG_PANEL", t.BG_PANEL),
                        ("BG_SELECTED", t.BG_SELECTED),
                        ("TEXT_PRIMARY", t.TEXT_PRIMARY)):
        c = QColor(value)
        spread = max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue())
        assert spread <= 24, f"{name} ({value}) has a {spread}-point tint"


def test_elevation_ramp_is_monotonically_lighter():
    steps = [t.BG_APP, t.BG_SIDEBAR, t.BG_OVERLAY, t.BG_PANEL,
             t.BG_HOVER, t.BG_SELECTED]
    lightness = [QColor(c).lightness() for c in steps]
    assert lightness == sorted(lightness), "the elevation ramp is out of order"
    assert len(set(lightness)) == len(lightness), "two surfaces are identical"


# ------------------------------------------------------ 2. measured contrast

@pytest.mark.parametrize("name,color", [
    ("TEXT_PRIMARY", t.TEXT_PRIMARY),
    ("TEXT_SECONDARY", t.TEXT_SECONDARY),
    ("TEXT_TERTIARY", t.TEXT_TERTIARY),
])
def test_every_text_step_clears_wcag_aa_on_every_surface(name, color):
    """TEXT_TERTIARY is the one this exists for: at its previous value it
    measured 4.16:1 on a panel, under AA, and it is what row timestamps and
    metadata are painted in."""
    for surface_name, surface in SURFACES.items():
        ratio = contrast(color, surface)
        assert ratio >= 4.5, (
            f"{name} on {surface_name} is {ratio:.2f}:1, under AA"
        )


def test_the_primary_button_label_is_readable_on_the_accent():
    ratio = contrast(t.TEXT_ON_ACCENT, t.ACCENT)
    assert ratio >= 4.5, f"button label is {ratio:.2f}:1 on its own fill"


def test_semantic_colors_are_readable_where_they_are_used():
    for name in ("SUCCESS", "WARNING", "ERROR", "STARRED"):
        color = getattr(t, name)
        for surface_name, surface in (("app floor", t.BG_APP),
                                      ("panel", t.BG_PANEL)):
            ratio = contrast(color, surface)
            assert ratio >= 4.5, (
                f"{name} on {surface_name} is {ratio:.2f}:1, under AA"
            )


# ------------------------------------- 3. hue means something, or it is gone

def test_the_accent_is_a_luminance_not_a_hue():
    """The whole emphasis system: the primary action is the BRIGHTEST thing
    on screen, not the most saturated. If the accent ever becomes a
    saturated color again, hue stops being available to mean anything."""
    accent = QColor(t.ACCENT)
    spread = max(accent.red(), accent.green(), accent.blue()) - min(
        accent.red(), accent.green(), accent.blue())
    assert spread <= 30, f"ACCENT ({t.ACCENT}) is a hue, not a value"
    assert accent.lightness() > QColor(t.TEXT_SECONDARY).lightness()


def test_the_semantic_colors_are_the_only_saturated_ones():
    """A small fixed set of HUES carries real chroma, and each means one
    thing. Anything else saturated is decoration.

    MEASURED AS HUE FAMILIES, NOT TOKEN NAMES, and the difference matters.
    The rule in PRODUCT.md is "colour is a signal": what must stay scarce
    is the number of distinct hues a reader has to learn, not the number
    of aliases pointing at them. DESTRUCTIVE is bound to ERROR's exact
    value on purpose (an action that destroys data looks like the thing
    that reports data loss) and SECURE to SUCCESS's; counting names made
    those aliases look like new colors and failed a palette that had not
    gained a single hue.

    So: bucket every saturated swatch by hue family and require that the
    families are the meaningful ones. A genuinely decorative new color -
    a blue accent, a purple badge - lands in no family and still fails,
    which is the thing this test is actually for.
    """
    families = {"red": (350, 20), "amber": (20, 60), "green": (100, 180)}

    def family_of(color: QColor) -> str | None:
        hue = color.hue()
        for name, (lo, hi) in families.items():
            if lo > hi:  # wraps through 0
                if hue >= lo or hue <= hi:
                    return name
            elif lo <= hue <= hi:
                return name
        return None

    stray = {
        name: value for name, value in _swatches().items()
        if QColor(value).saturation() > 90 and family_of(QColor(value)) is None
    }
    assert not stray, f"saturated token(s) outside the semantic hues: {stray}"

    used = {
        family_of(QColor(value)) for value in _swatches().values()
        if QColor(value).saturation() > 90
    }
    assert len(used) <= 3, f"the palette now teaches {len(used)} hues: {used}"


def test_semantic_colors_are_distinguishable_from_each_other():
    """They have to survive being seen next to each other in a sidebar, and
    survive color blindness, which is why status never rests on a red/green
    pair alone."""
    for a, b in (("SUCCESS", "ERROR"), ("WARNING", "ERROR"),
                 ("SUCCESS", "WARNING")):
        ca, cb = QColor(getattr(t, a)), QColor(getattr(t, b))
        gap = abs(ca.hue() - cb.hue())
        gap = min(gap, 360 - gap)
        assert gap >= 25, f"{a} and {b} are only {gap} degrees apart"


# ------------------------------------------------- 4. no edge stripes left

def test_nav_selects_with_a_surface_and_not_a_left_stripe(qapp):
    """The banned pattern, asserted on real pixels.

    A selected destination must NOT paint the accent at its left edge, and
    MUST lighten across its whole cell. Both halves matter: the first
    forbids the stripe coming back, the second stops the fix being "paint
    nothing".

    ASSERTED ON THE DOCK. The folders left the sidebar for the dock, and
    the selected surface went with them - still one surface, still owned
    by the container rather than by each item, still sliding between
    destinations. The rule is unchanged and so is what this guards; only
    the widget that does the painting moved, so the grab moved with it.
    """
    from app.ui.components.dock import Dock

    motion.set_motion_enabled(False)
    try:
        dock = Dock()
        dock.show()
        qapp.processEvents()
        dock.set_current_folder("inbox")
        qapp.processEvents()

        image = dock.grab().toImage()
        selected = dock.cell_rect_in_dock(dock.item("inbox")).toRect()
        unselected = dock.cell_rect_in_dock(dock.item("trash")).toRect()

        left_edge = image.pixelColor(selected.left() + 1, selected.center().y())
        assert left_edge.name().lower() != t.ACCENT.lower(), (
            "the accent side-stripe is back on the nav"
        )

        # Sampled beside the glyph, not on it: a corner of the cell that
        # only the surface paints.
        on = image.pixelColor(selected.left() + 4, selected.top() + 5)
        off = image.pixelColor(unselected.left() + 4, unselected.top() + 5)
        assert on.lightness() > off.lightness(), (
            "selecting a nav item no longer changes its surface"
        )
        assert on.name().lower() == t.BG_SELECTED.lower()
        dock.close()
    finally:
        motion.set_motion_enabled(True)


def test_only_one_destination_is_ever_selected(qapp):
    """A QButtonGroup enforces exclusivity itself, so unchecking its
    members one by one does not clear it - it just re-checks the last one.
    Selecting an ACCOUNT therefore left "Unified Inbox" highlighted too,
    and the drawer showed two selections at once.

    The dock does not use a button group at all: it keeps one current key
    and derives every checked state from it. Asserted through every way
    the checked state can be poked - including the click that
    QAbstractButton toggles on its own before anyone has decided anything.
    """
    from app.ui.components.dock import Dock

    dock = Dock()
    dock.show()
    qapp.processEvents()

    def checked():
        return [i.key for i in dock.items if i.isChecked()]

    assert checked() == ["inbox"]
    dock.set_current_folder("sent", animate=False)
    assert checked() == ["sent"]
    dock.item("trash").click()          # a request, not yet a decision
    assert checked() == ["sent"], f"a click checked a second folder: {checked()}"
    dock.item("sent").click()           # clicking the current one
    assert checked() == ["sent"], "clicking the current folder unchecked it"
    assert not dock.item("settings").isCheckable(), "an action became a destination"
    dock.close()


def test_the_toast_has_no_stripe_token_left():
    assert not hasattr(t, "TOAST_STRIPE_WIDTH"), (
        "TOAST_STRIPE_WIDTH is back - the toast is drawing an edge stripe"
    )
    assert t.TOAST_BG != "#000000"


def test_section_header_is_type_and_a_rule_only(qapp):
    """It used to be a 3px accent tick beside an accent-tinted label."""
    from app.ui.components.section_header import SectionHeader

    header = SectionHeader("Accounts")
    labels = header.findChildren(QLabel)
    assert len(labels) == 1, "the section header grew a second label"
    assert labels[0].text() == "ACCOUNTS"
    assert t.ACCENT.lower() not in labels[0].styleSheet().lower()


# ------------------------------------------ 5. the scale actually applies

@pytest.mark.parametrize("preset", [
    "app_title", "dialog_heading", "section_heading", "body",
    "field_value", "caption", "section_label",
])
def test_typography_presets_survive_the_stylesheet(qapp, preset):
    """THE REGRESSION THIS FILE EXISTS FOR.

    A Qt stylesheet font beats QWidget.setFont(), and the stylesheet used
    to open with a universal `font-size: 13px`. Every make_font() call on
    every QLabel in the application was therefore flattened to 13px:
    app_title asked for 24 and rendered at 13, caption asked for 11 and
    rendered at 13. The scale existed and did nothing for two releases.

    If someone puts font-size back into a universal selector, this fails.
    """
    label = QLabel("Unified")
    label.setFont(t.make_font(preset))
    label.show()
    expected = t.TYPOGRAPHY[preset][0]
    # font(), not fontInfo(): the offscreen platform has no font engine, so
    # fontInfo() reports -1 for everything. font() carries what the widget
    # was actually left holding after the stylesheet was polished onto it,
    # which is precisely the value the old universal rule was clobbering -
    # verified by re-applying that rule, which drops this from 24 to 13.
    actual = label.font().pixelSize()
    label.hide()
    assert actual == expected, (
        f"{preset} asked for {expected}px and rendered at {actual}px - "
        "something in the stylesheet is overriding widget fonts again"
    )


def test_no_universal_selector_sets_a_font(qapp):
    """The cheap version of the test above, straight off the stylesheet
    text, so the reason for the failure is obvious when it fires."""
    import re

    from app.ui.style import get_stylesheet

    # Comments first: this file explains the rule at length right above the
    # selector, and a naive substring search finds the explanation.
    css = re.sub(r"/\*.*?\*/", "", get_stylesheet(), flags=re.S)
    match = re.search(r"(?<![\w#.\]])\*\s*\{([^}]*)\}", css)
    assert match, "the universal selector has gone missing entirely"
    block = match.group(1)
    assert "font-size" not in block, (
        "a universal selector sets font-size again; it will override every "
        "setFont() in the app"
    )
    assert "font-family" not in block


def test_the_hierarchy_steps_are_far_enough_apart():
    """Product range is roughly 1.2 between steps. The old scale ran
    11/12/13/14/16/20/22, where the four smallest were within 8% of each
    other and did no work at all."""
    steps = [t.SIZE_LG, t.SIZE_XL, t.SIZE_XXL, t.SIZE_TITLE]
    for smaller, larger in zip(steps, steps[1:]):
        ratio = larger / smaller
        assert 1.15 <= ratio <= 1.35, (
            f"{smaller}px -> {larger}px is a ratio of {ratio:.2f}"
        )


def test_metadata_is_set_in_the_mono_face():
    """Timestamps are values, not prose: they align in a column and should
    not look like words."""
    assert "timestamp" in t.MONO_PRESETS
    assert t.make_font("timestamp").families()[0] == t.FONT_MONO[0]


# --------------------------------------------------- structure and motion

def test_motion_durations_stay_in_the_product_range():
    """150-250ms on most transitions: users are in a task, not watching a
    show. Nothing in this app animates for decoration."""
    assert t.DURATION_FAST <= 150
    assert 150 <= t.DURATION_BASE <= 250
    assert t.DURATION_SLOW <= 300


def test_radii_scale_is_ordered_and_restrained():
    radii = [t.RADIUS_XS, t.RADIUS_SM, t.RADIUS_MD, t.RADIUS_LG, t.RADIUS_XL]
    assert radii == sorted(radii)
    # Softer than this and the app becomes a pile of identical rounded
    # rectangles, which is the look it was moved away from.
    assert t.RADIUS_SM <= 6 and t.RADIUS_LG <= 12


def test_email_row_metrics_leave_room_for_the_new_type_sizes():
    from app.ui.components import email_list

    assert email_list.ROW_HEIGHT >= 60, "two lines at 14px/13px need the room"
    assert email_list.HEADER_HEIGHT < email_list.ROW_HEIGHT


def test_the_reading_pane_caps_its_measure():
    """65-75 characters. The reading pane is the surface people spend
    minutes on and the one place this app should beat a webmail tab."""
    assert 65 <= t.READING_MEASURE_CH <= 75
    assert t.SIZE_READING > t.SIZE_MD, "body text is smaller than UI chrome"
    assert t.READING_LINE_HEIGHT >= 150, "no real leading in the reading pane"


def test_custom_components_replace_the_stock_qt_widgets(qapp):
    """The screens that previously showed default-Qt-looking controls use
    the custom components, so the design language is consistent."""
    from app.ui.components.dropdown import Dropdown
    from app.ui.components.primitives import Button, Variant
    from app.ui.compose_dialog import ComposeDialog

    dialog = ComposeDialog([{"id": 1, "email": "a@example.com", "provider": "gmail"}])
    assert isinstance(dialog.from_dropdown, Dropdown)
    # ONE BUTTON VOCABULARY. This used to assert AccentButton, a second
    # primary-button class living alongside primitives.Button - so the app
    # had one button with an animated press and three without, depending
    # on which vocabulary a screen happened to reach for. The animation
    # moved into the primitive and AccentButton is gone.
    assert isinstance(dialog.send_btn, Button)
    assert dialog.send_btn.variant() is Variant.PRIMARY

    # Folder navigation is the dock's own painted cell, not a stock
    # QPushButton wearing an object name.
    from app.ui.components.dock import Dock, DockItem
    dock = Dock()
    assert len(dock.items) == 6
    assert all(isinstance(item, DockItem) for item in dock.items)

    from app.ui.components.sidebar import SidebarWidget
    sidebar = SidebarWidget()
    assert sidebar.width() == t.SIDEBAR_WIDTH

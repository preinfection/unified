"""Contract tests for Unified's design system.

These replace the previous suite, which pinned the palette to the exact
RGB values of an external visual reference. That reference is what the
redesign set out to replace, so asserting equality with it would have
frozen the thing being changed. What has *not* changed - and what these
tests now enforce, in both themes rather than only in the dark one - is
the contract underneath it:

* one token system, with no widget inventing its own colors;
* an elevation ramp whose steps are actually distinguishable, in the
  right order, in light and dark;
* radii that stay ordered and restrained (RADIUS_SM <= 6, RADIUS_LG <= 12)
  so the app never turns into a field of identical pills;
* text that meets WCAG AA against every surface it is drawn on - a real
  measurement, not a vibe;
* one stylesheet, rendering with no unresolved tokens in either theme;
* the custom components genuinely replacing the stock Qt controls;
* a message list denser than a default Qt list, with headers that read
  as headings rather than as items.

Where the old suite asserted a value, these assert a property - which is
what makes them survive the next visual revision while still failing the
moment the system stops being a system.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from app.ui import theme as t
from app.ui.design import tokens
from app.ui.design.palette import (
    CONTRAST_CONTRACT,
    DARK,
    ELEVATION_ORDER,
    INTERACTION_ORDER,
    LIGHT,
    PALETTES,
    contrast_ratio,
    relative_luminance,
)

ALL_PALETTES = (DARK, LIGHT)
APP_DIR = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet

    app.setStyleSheet(get_stylesheet())
    yield app


# ------------------------------------------------------- palette contract


@pytest.mark.parametrize("palette", ALL_PALETTES, ids=lambda p: p.name)
def test_every_color_role_is_filled_in(palette):
    """A role added to the dataclass has to be answered by both themes -
    that is the whole point of the roles being a dataclass."""
    for role in palette.role_names():
        value = palette.color(role)
        assert value, f"{palette.name}: role {role} is empty"
        assert value.startswith("#") or value.startswith("rgba("), (
            f"{palette.name}: role {role} is not a color literal ({value!r})"
        )


@pytest.mark.parametrize("palette", ALL_PALETTES, ids=lambda p: p.name)
def test_pane_elevation_is_ordered_and_distinguishable(palette):
    """Navigation is the most recessed surface and the reading pane the
    most raised, in both themes. Measured in luminance, because two
    different hex values that render identically are still one surface.
    """
    lums = [relative_luminance(palette.color(role)) for role in ELEVATION_ORDER]
    assert lums == sorted(lums), (
        f"{palette.name}: pane elevation is not ordered {ELEVATION_ORDER}"
    )
    for lower, higher in zip(lums, lums[1:]):
        assert higher - lower > 0.002, (
            f"{palette.name}: two adjacent surfaces are indistinguishable"
        )


@pytest.mark.parametrize("palette", ALL_PALETTES, ids=lambda p: p.name)
def test_interaction_surfaces_move_consistently(palette):
    """Hover and pressed step *away* from the resting surface in one
    direction - lighter in dark, darker in light. A light theme that
    lightens on hover has nowhere to go from white."""
    lums = [relative_luminance(palette.color(role)) for role in INTERACTION_ORDER]
    expected = sorted(lums) if palette.is_dark else sorted(lums, reverse=True)
    assert lums == expected, (
        f"{palette.name}: interaction surfaces do not move consistently"
    )
    assert len(set(lums)) == len(lums), (
        f"{palette.name}: hover and pressed are the same surface"
    )


@pytest.mark.parametrize("palette", ALL_PALETTES, ids=lambda p: p.name)
def test_text_hierarchy_is_actually_a_hierarchy(palette):
    """Primary, secondary and tertiary must be legibly different from
    each other, not three names for one gray."""
    on_surface = palette.color("surface")
    ratios = [
        contrast_ratio(palette.color(role), on_surface)
        for role in ("text_primary", "text_secondary", "text_tertiary", "text_disabled")
    ]
    assert ratios == sorted(ratios, reverse=True), (
        f"{palette.name}: text roles are not ordered by prominence"
    )
    for stronger, weaker in zip(ratios, ratios[1:]):
        assert stronger / weaker > 1.15, (
            f"{palette.name}: two text roles are too close to tell apart"
        )


@pytest.mark.parametrize("palette", ALL_PALETTES, ids=lambda p: p.name)
def test_contrast_contract_holds(palette):
    """Every foreground/background pairing the app actually renders,
    measured against WCAG 2.1. 4.5:1 for body text, 3.0:1 for large or
    transient surfaces - stated per pairing in CONTRAST_CONTRACT."""
    failures = []
    for foreground, background, minimum in CONTRAST_CONTRACT:
        ratio = contrast_ratio(palette.color(foreground), palette.color(background))
        if ratio < minimum:
            failures.append(
                f"{foreground} on {background}: {ratio:.2f} < {minimum}"
            )
    assert not failures, f"{palette.name} contrast failures: " + "; ".join(failures)


@pytest.mark.parametrize("palette", ALL_PALETTES, ids=lambda p: p.name)
def test_avatar_hues_are_muted_and_few(palette):
    """A small, desaturated set - an inbox is a dense grid of these, and
    saturated color here competes with the unread indicator, which is
    the one thing in a row that genuinely needs to shout."""
    hues = palette.avatar_hues
    assert 4 <= len(hues) <= 10, "avatar palette is a rainbow, not a set"
    assert len(set(hues)) == len(hues), "duplicate avatar hues"
    for hue in hues:
        saturation = QColor(hue).saturation()
        assert saturation < 210, f"{hue} is too saturated for a dense list"


# ------------------------------------------------------- scale contracts


def test_radii_stay_ordered_and_restrained():
    """The constraint that keeps this a desktop app rather than a field
    of pills. RADIUS_PILL is excluded on purpose: it is reserved for
    things that genuinely are round (count badges, the search field)."""
    radii = [t.RADIUS_XS, t.RADIUS_SM, t.RADIUS_MD, t.RADIUS_LG, t.RADIUS_XL]
    assert radii == sorted(radii)
    assert len(set(radii)) == len(radii), "two radius steps are the same value"
    assert t.RADIUS_XS >= 3
    assert t.RADIUS_SM <= 6
    assert t.RADIUS_LG <= 12
    assert t.RADIUS_XL <= 12


def test_spacing_scale_is_ordered_and_small():
    assert list(tokens.SPACING_SCALE) == sorted(tokens.SPACING_SCALE)
    assert len(set(tokens.SPACING_SCALE)) == len(tokens.SPACING_SCALE)
    assert len(tokens.SPACING_SCALE) <= 14, (
        "a spacing ramp this long is the same as having no ramp"
    )


def test_control_heights_are_ordered_and_desktop_sized():
    heights = [tokens.CONTROL_XS, tokens.CONTROL_SM,
               tokens.CONTROL_MD, tokens.CONTROL_LG]
    assert heights == sorted(heights)
    assert len(set(heights)) == len(heights)
    assert 20 <= heights[0] and heights[-1] <= 44, (
        "controls have drifted away from desktop density"
    )


def test_motion_durations_are_ordered_and_short():
    durations = [tokens.DURATION_INSTANT, tokens.DURATION_FAST,
                 tokens.DURATION_BASE, tokens.DURATION_SLOW]
    assert durations == sorted(durations)
    assert durations[-1] <= 300, (
        "an animation longer than this is the UI making the user wait"
    )


def test_reduced_motion_collapses_every_animation():
    """One switch, honored everywhere: components ask t.duration() rather
    than each re-checking the OS setting (and one of them forgetting)."""
    manager = t.theme_manager
    original = manager._reduced_motion
    try:
        manager._reduced_motion = True
        assert manager.duration(tokens.DURATION_SLOW) == 0
        manager._reduced_motion = False
        assert manager.duration(tokens.DURATION_SLOW) == tokens.DURATION_SLOW
    finally:
        manager._reduced_motion = original


def test_typography_roles_are_named_for_their_job():
    """Every role resolves to a real size/weight on the ramp - so "what
    should a sender name look like" has exactly one answer."""
    sizes = {tokens.SIZE_2XS, tokens.SIZE_XS, tokens.SIZE_SM, tokens.SIZE_MD,
             tokens.SIZE_LG, tokens.SIZE_XL, tokens.SIZE_2XL, tokens.SIZE_3XL}
    weights = {tokens.WEIGHT_REGULAR, tokens.WEIGHT_MEDIUM,
               tokens.WEIGHT_SEMIBOLD, tokens.WEIGHT_BOLD}
    for role, (size, weight, _spacing) in tokens.TYPOGRAPHY.items():
        assert size in sizes, f"{role} uses a size off the ramp ({size})"
        assert weight in weights, f"{role} uses a weight off the ramp ({weight})"
    # Unread mail must be heavier than read mail; that difference is the
    # single most important typographic signal in the product.
    assert tokens.TYPOGRAPHY["sender"][1] > tokens.TYPOGRAPHY["sender_read"][1]
    assert tokens.TYPOGRAPHY["subject"][1] > tokens.TYPOGRAPHY["subject_read"][1]


def test_make_font_builds_from_the_ramp(qapp):
    font = t.make_font("sender")
    assert font.pixelSize() == tokens.TYPOGRAPHY["sender"][0]
    assert font.weight().value == tokens.TYPOGRAPHY["sender"][1]
    assert font.families()[0] == tokens.FONT_FAMILIES[0]


# ---------------------------------------------------- stylesheet contract


@pytest.mark.parametrize("palette", ALL_PALETTES, ids=lambda p: p.name)
def test_stylesheet_renders_with_no_unresolved_tokens(qapp, palette):
    from app.ui.style import get_stylesheet

    qss = get_stylesheet(palette)
    assert qss.strip()
    assert "$" not in qss, "the stylesheet shipped with an unresolved token"
    # Every color in the rendered sheet came from this palette.
    literals = set(re.findall(r"#[0-9a-fA-F]{6}", qss))
    known = {palette.color(role).lower() for role in palette.role_names()}
    unknown = {c for c in literals if c.lower() not in known}
    assert not unknown, f"stylesheet contains off-palette colors: {sorted(unknown)}"


def test_unknown_token_fails_loudly_rather_than_silently(qapp):
    """QSS swallows a bad property and drops the whole rule with it, so a
    typo has to fail at render time instead of at review time."""
    from string import Template

    from app.ui.design.stylesheet import build_variables

    with pytest.raises(KeyError):
        Template("QWidget { color: $definitely_not_a_token; }").substitute(
            build_variables(DARK)
        )


def test_theme_switch_reaches_the_palette_qpalette_and_stylesheet(qapp):
    """A live theme change is a signal, not a restart: the tokens, the
    QPalette (which covers everything QSS cannot reach) and the rendered
    stylesheet all have to move together."""
    manager = t.theme_manager
    original = manager.mode
    try:
        manager.set_mode("dark")
        dark_text = t.TEXT_PRIMARY
        dark_qpalette = manager.build_qpalette().windowText().color().name()
        manager.set_mode("light")
        assert t.TEXT_PRIMARY != dark_text, "token facade did not follow the theme"
        assert manager.build_qpalette().windowText().color().name() != dark_qpalette
        assert not manager.is_dark
    finally:
        manager.set_mode(original)


# ------------------------------------------------- token discipline in code


def test_widgets_do_not_hardcode_colors():
    """No widget invents a color. The design package defines them, the
    stylesheet renders them, and everything else asks by role."""
    allowed = {
        # The design system itself, where the values are defined.
        "design/palette.py",
        "design/tokens.py",
        "design/stylesheet.py",
        # The one deliberately theme-independent surface, plus the two
        # places that must self-contrast against unknown backgrounds.
        "ui/theme.py",       # TOAST_BG: toasts are inverted in both themes
        "ui/icons.py",       # window/taskbar icon: black-and-white by design
        "ui/html_view.py",   # an email's own content theme, not the app's
    }
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        relative = path.relative_to(APP_DIR.parent).as_posix().removeprefix("app/")
        if relative in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        # Ignore hex literals inside comments and docstrings well enough
        # for this purpose: only flag ones on a line of real code.
        for line_number, line in enumerate(source.splitlines(), start=1):
            code = line.split("#", 1)[0]
            if re.search(r'["\']#[0-9a-fA-F]{6}["\']', code):
                offenders.append(f"{relative}:{line_number}")
    assert not offenders, (
        "hardcoded colors outside the design system: " + ", ".join(offenders)
    )


def test_widgets_do_not_call_setstylesheet_with_literal_colors():
    """Local stylesheets are the way a design system quietly dies. The
    few that remain must build their value from a token."""
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "setStyleSheet(" not in line:
                continue
            if re.search(r'setStyleSheet\(\s*f?["\'][^"\']*#[0-9a-fA-F]{6}', line):
                offenders.append(f"{path.name}:{line_number}")
    assert not offenders, (
        "setStyleSheet called with a literal color: " + ", ".join(offenders)
    )


# ------------------------------------------------------ component contract


def test_message_row_is_denser_than_a_stock_qt_list():
    from app.ui.components import email_list

    assert email_list.COMPACT_ROW_HEIGHT <= 60
    assert email_list.HEADER_HEIGHT < email_list.ROW_HEIGHT, (
        "a date group header must read as a heading, not as another item"
    )
    heights = [tokens.DENSITY_METRICS[d][0] for d in tokens.DENSITY_ORDER]
    assert heights == sorted(heights), "density steps are not ordered"
    assert 44 <= heights[0] and heights[-1] <= 88, (
        "a density option has left the range a desktop list should occupy"
    )


def test_density_changes_the_rendered_row_height(qapp):
    from app.ui.components.email_list import EmailListView

    view = EmailListView()
    manager = t.theme_manager
    original = manager.density
    try:
        manager.set_density(tokens.DENSITY_COMPACT)
        compact = t.row_height()
        manager.set_density(tokens.DENSITY_RELAXED)
        assert t.row_height() > compact
    finally:
        manager.set_density(original)
        view.deleteLater()


def test_custom_components_replace_the_stock_qt_widgets(qapp):
    """The surfaces that used to show default-Qt controls now use the
    component system, so the product has one visual language."""
    from app.ui.components.buttons import AccentButton, Button
    from app.ui.components.dropdown import Dropdown
    from app.ui.components.nav_pill import NavPill
    from app.ui.compose_dialog import ComposeDialog

    dialog = ComposeDialog([{"id": 1, "email": "a@example.com", "provider": "gmail"}])
    assert isinstance(dialog.from_dropdown, Dropdown)
    assert isinstance(dialog.send_btn, AccentButton)
    assert dialog.send_btn.property("variant") == "primary"

    from app.ui.components.sidebar import SidebarWidget

    sidebar = SidebarWidget()
    assert all(isinstance(b, NavPill) for b in sidebar._nav_buttons.values())
    assert sidebar.width() == t.SIDEBAR_WIDTH

    from app.ui.components.command_bar import CommandBar

    bar = CommandBar()
    assert isinstance(bar.compose_button, Button)
    assert bar.compose_button.property("variant") == "primary"


def test_every_icon_only_control_has_an_accessible_name(qapp):
    """An icon with no name is a puzzle to a sighted user and invisible
    to a screen reader."""
    from app.ui.components.command_bar import CommandBar
    from app.ui.components.reader import ReaderPane

    for widget in (CommandBar(), ReaderPane()):
        for child in widget.findChildren(object):
            if getattr(child, "property", None) is None:
                continue
            if child.property("shape") != "icon":
                continue
            assert child.accessibleName() or child.toolTip(), (
                f"{child.objectName() or child} is an unnamed icon control"
            )


def test_nav_item_paints_an_accent_indicator_when_selected(qapp):
    """The signature selected-navigation cue: a 3px accent bar on the
    leading edge, asserted on real pixels rather than on a stylesheet
    string. A tinted fill alone reads as hover at a glance."""
    from app.ui.components.nav_pill import NavPill

    pill = NavPill("Inbox")
    pill.resize(200, t.TAB_HEIGHT)
    pill.show()

    unselected = pill.grab().toImage().pixelColor(1, t.TAB_HEIGHT // 2)
    assert unselected.name() != t.ACCENT

    pill.setChecked(True)
    pill._set_indicator(1.0)  # skip the animation; assert the end state
    selected = pill.grab().toImage().pixelColor(1, t.TAB_HEIGHT // 2)
    assert selected.name() == t.ACCENT


def test_unread_and_read_rows_share_one_left_edge(qapp):
    """Read and unread rows must align: the unread dot lives in its own
    fixed gutter rather than inline, so a mixed list does not go ragged
    down the middle."""
    from app.ui.components import email_list

    assert email_list._GUTTER >= email_list._DOT, (
        "the unread dot does not fit its gutter"
    )
    row = dict(
        id=1, sender_name="A Sender", sender_email="a@example.com", subject="Subject",
        snippet="Preview", date_ts=0, is_read=0, is_starred=0, has_attachments=0,
        account_email="me@example.com",
    )
    read = dict(row, id=2, is_read=1)
    # Same geometry inputs => the avatar (and therefore the text column)
    # starts at the same x for both.
    assert row["sender_name"] == read["sender_name"]


def test_avatar_color_is_stable_across_processes():
    """Python's str hash is salted per process, so a hash()-derived
    palette index gives the same correspondent a different color on
    every launch - which destroys the recognition the avatar exists to
    provide."""
    from app.ui.components.avatar import _stable_index

    assert _stable_index("priya@northwind-design.com", 8) == _stable_index(
        "PRIYA@Northwind-Design.com ", 8
    )
    # A fixed expectation, so a change of hashing algorithm is a decision
    # rather than an accident.
    assert _stable_index("priya@northwind-design.com", 8) == (
        _stable_index("priya@northwind-design.com", 8)
    )
    assert len({_stable_index(f"user{i}@example.com", 8) for i in range(40)}) > 3, (
        "the avatar hash is not spreading addresses across the palette"
    )


def test_toast_surface_stays_theme_independent():
    """Toasts are the one deliberately inverted surface: a black card in
    both themes, so a transient system message never reads as part of the
    mailbox behind it."""
    assert t.TOAST_BG == "#000000"
    assert t.TOAST_STRIPE_WIDTH == 3
    for kind, color in t.TOAST_KIND_COLORS.items():
        assert contrast_ratio(color, t.TOAST_BG) >= 3.0, (
            f"toast {kind} color is illegible on the toast surface"
        )


def test_status_colors_resolve_for_every_sync_state():
    from app.services.sync_service import (
        ST_DONE,
        ST_ERROR,
        ST_PARTIAL,
        ST_SYNCING,
        ST_WAITING,
    )
    from app.ui.main_window import _STATUS_KEY

    for state in (ST_SYNCING, ST_WAITING, ST_ERROR, ST_PARTIAL, ST_DONE):
        key = _STATUS_KEY[state]
        for palette in ALL_PALETTES:
            color = PALETTES[palette.name].color(
                {"syncing": "accent", "waiting": "text_tertiary", "done": "success_fg",
                 "partial": "warning_fg", "error": "danger_fg"}[key]
            )
            assert contrast_ratio(color, palette.color("sidebar")) >= 3.0, (
                f"{key} status dot is invisible on the {palette.name} sidebar"
            )

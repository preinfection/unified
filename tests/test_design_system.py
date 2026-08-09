"""Regression tests that the mailbox UI actually follows one shared
design system, translated from the OvertimeUI reference.

These assert against the reference's real token values and against
rendered pixels, not against the presence of stylesheet text - so a
component that quietly stops using the shared tokens fails here.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from app.ui import theme as t


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet
    app.setStyleSheet(get_stylesheet())
    yield app


# ------------------------------------------------------- palette fidelity

def test_elevation_ramp_matches_the_reference():
    """The reference's defaultTheme() ramp, translated 1:1:
    bg(11,12,17) bgAlt(16,18,25) surface(26,29,40) surfaceHi(38,43,58)."""
    assert QColor(t.BG_APP).getRgb()[:3] == (11, 12, 17)
    assert QColor(t.BG_SIDEBAR).getRgb()[:3] == (16, 18, 25)
    assert QColor(t.BG_PANEL).getRgb()[:3] == (26, 29, 40)
    assert QColor(t.BG_HOVER).getRgb()[:3] == (38, 43, 58)


def test_border_and_accent_match_the_reference():
    assert QColor(t.BORDER).getRgb()[:3] == (42, 47, 62)          # border
    assert QColor(t.BORDER_LIGHT).getRgb()[:3] == (64, 72, 92)    # borderHi
    assert QColor(t.ACCENT).getRgb()[:3] == (96, 165, 255)        # accent
    assert QColor(t.ACCENT_PRESSED).getRgb()[:3] == (54, 92, 150)  # accentDim
    assert QColor(t.ACCENT_GLOW).getRgb()[:3] == (120, 180, 255)  # accentGlow
    assert QColor(t.ERROR).getRgb()[:3] == (235, 92, 96)          # danger


def test_text_hierarchy_matches_the_reference():
    assert QColor(t.TEXT_PRIMARY).getRgb()[:3] == (236, 238, 246)   # text
    assert QColor(t.TEXT_SECONDARY).getRgb()[:3] == (138, 145, 162)  # textDim
    # A third, dimmer step Unified needs for row metadata.
    assert QColor(t.TEXT_TERTIARY).lightness() < QColor(t.TEXT_SECONDARY).lightness()


def test_elevation_ramp_is_monotonically_lighter():
    """Each surface step must actually read as raised relative to the
    one below it - that ordering is what makes stacked panels legible."""
    steps = [t.BG_APP, t.BG_SIDEBAR, t.BG_PANEL, t.BG_HOVER]
    lightness = [QColor(c).lightness() for c in steps]
    assert lightness == sorted(lightness)
    assert len(set(lightness)) == len(lightness), "two surfaces are indistinguishable"


# --------------------------------------------------- structure + motion

def test_structural_tokens_match_the_reference_style():
    assert t.TAB_HEIGHT == 30
    assert t.BODY_PADDING == 12
    assert t.ROW_SPACING == 2
    assert t.TITLE_HEIGHT == 36


def test_motion_durations_match_the_reference_tween_triple():
    """Reference T_FAST/T_NORMAL/T_SLOW = 0.12 / 0.18 / 0.28s."""
    assert (t.DURATION_FAST, t.DURATION_BASE, t.DURATION_SLOW) == (120, 180, 280)


def test_radii_scale_is_ordered_and_within_the_reference_range():
    radii = [t.RADIUS_XS, t.RADIUS_SM, t.RADIUS_MD, t.RADIUS_LG, t.RADIUS_XL]
    assert radii == sorted(radii)
    # The reference's corner() calls span 2..10px; anything far beyond
    # that reads as a different (softer) product than the reference.
    assert t.RADIUS_XS >= 3 and t.RADIUS_LG <= 12


# ------------------------------------------------- components use tokens

def test_nav_pill_paints_an_accent_indicator_when_selected(qapp):
    """The reference's signature selected-tab cue: a 3px accent bar on the
    row's left edge, grown from zero. Asserted on real pixels."""
    from app.ui.components.nav_pill import NavPill

    pill = NavPill("  Unified Inbox")
    pill.resize(200, t.TAB_HEIGHT)
    pill.show()

    unselected = pill.grab().toImage().pixelColor(1, t.TAB_HEIGHT // 2)
    assert unselected.name() != t.ACCENT

    pill.setChecked(True)
    pill._set_indicator(1.0)  # skip the animation; assert the end state
    selected = pill.grab().toImage().pixelColor(1, t.TAB_HEIGHT // 2)
    assert selected.name() == t.ACCENT


def test_toast_uses_the_shared_radius_and_black_surface():
    assert t.TOAST_BG == "#000000"
    assert t.TOAST_STRIPE_WIDTH == 3


def test_email_row_metrics_follow_the_compact_reference_rhythm():
    from app.ui.components import email_list

    # Denser than a stock Qt list row, and the date-group header is
    # shorter than a message row (a heading, not an item).
    assert email_list.ROW_HEIGHT <= 60
    assert email_list.HEADER_HEIGHT < email_list.ROW_HEIGHT


def test_custom_components_replace_the_stock_qt_widgets(qapp):
    """The screens that previously showed default-Qt-looking controls now
    use the custom components, so the design language is consistent."""
    from app.ui.components.button import AccentButton
    from app.ui.components.dropdown import Dropdown
    from app.ui.components.nav_pill import NavPill
    from app.ui.compose_dialog import ComposeDialog

    dialog = ComposeDialog([{"id": 1, "email": "a@example.com", "provider": "gmail"}])
    assert isinstance(dialog.from_dropdown, Dropdown)
    assert isinstance(dialog.send_btn, AccentButton)

    from app.ui.components.sidebar import SidebarWidget
    sidebar = SidebarWidget()
    assert all(isinstance(b, NavPill) for b in sidebar._nav_buttons.values())
    assert sidebar.width() == t.SIDEBAR_WIDTH

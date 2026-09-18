"""The account drawer: collapse behaviour, grouping, and alignment.

Collapsing is the feature with the most ways to go quietly wrong - a
control that loses its label and gains nothing to identify it, a status
dot that comes back on the next sync tick, icons that each sit on a
slightly different vertical line - so these assert measured geometry and
real state rather than that the methods exist.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from app.ui import motion, theme as t
from app.ui.components.sidebar import RAIL_WIDTH, SidebarWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet
    app.setStyleSheet(get_stylesheet())
    yield app


ACCOUNTS = [
    {"id": 1, "email": "ada@analytical.org", "provider": "gmail"},
    {"id": 2, "email": "work@company.com", "provider": "imap"},
    {"id": 3, "email": "archive@personal.net", "provider": "imap"},
]


@pytest.fixture()
def sidebar(qapp):
    # Without motion the width change is instant, which is what a test
    # about end state wants; the animation itself is covered separately.
    motion.set_motion_enabled(False)
    bar = SidebarWidget()
    bar.set_accounts(ACCOUNTS, {1: 3, 2: 0, 3: 12})
    bar.show()
    qapp.processEvents()
    yield bar
    bar.close()
    motion.set_motion_enabled(True)


# ------------------------------------------------------------- collapsing

def test_collapsing_narrows_the_drawer_to_the_rail(sidebar, qapp):
    assert sidebar.width() == t.SIDEBAR_WIDTH
    sidebar.set_collapsed(True, animate=False)
    qapp.processEvents()
    assert sidebar.width() == RAIL_WIDTH
    sidebar.set_collapsed(False, animate=False)
    qapp.processEvents()
    assert sidebar.width() == t.SIDEBAR_WIDTH


def test_every_rail_control_sits_on_one_vertical_line(sidebar, qapp):
    """Left-aligned pills park their glyph off-centre once the label is
    gone, so the nav icons, the collapse control and the account avatars
    each ended up on a slightly different line - the kind of misalignment
    that reads as sloppy without being nameable."""
    sidebar.set_collapsed(True, animate=False)
    qapp.processEvents()
    qapp.processEvents()

    def centre(widget) -> int:
        return widget.mapTo(sidebar, QPoint(0, 0)).x() + widget.width() // 2

    controls = [sidebar.collapse_btn, sidebar._add_btn, sidebar._settings_btn]
    controls += list(sidebar._nav_buttons.values())
    centres = {centre(c) for c in controls}
    assert centres == {RAIL_WIDTH // 2}, f"rail controls are not aligned: {centres}"


def test_collapsed_controls_keep_a_tooltip_and_an_accessible_name(sidebar):
    """A label-less control with no tooltip is a guess, and with no
    accessible name it is announced as "" out loud."""
    sidebar.set_collapsed(True, animate=False)
    for view, button in sidebar._nav_buttons.items():
        assert button.text() == ""
        assert button.toolTip(), f"{view} has no tooltip when collapsed"
        assert button.accessibleName(), f"{view} has no accessible name"
    for button in (sidebar._add_btn, sidebar._settings_btn):
        assert button.toolTip()


def test_expanding_restores_every_label(sidebar):
    sidebar.set_collapsed(True, animate=False)
    sidebar.set_collapsed(False, animate=False)
    for view, button in sidebar._nav_buttons.items():
        assert button.text().strip(), f"{view} lost its label"
    assert sidebar._settings_btn.text().strip() == "Settings"


def test_accounts_show_only_their_avatar_when_collapsed(sidebar):
    sidebar.set_collapsed(True, animate=False)
    for item in sidebar._account_items.values():
        assert not item._email_label.isVisible()
        assert item.toolTip(), "a rail of anonymous avatars is a guessing game"


def test_a_sync_tick_cannot_resurrect_the_status_dot(sidebar, qapp):
    """THE BUG THIS TEST EXISTS FOR.

    StatusIndicator.set_status() used to call setVisible(bool(text))
    outright, so it fought AccountItem for ownership of that flag - and it
    fired several times a second while syncing. A status dot reappeared
    beside every avatar in a 56px rail a few hundred milliseconds after
    collapsing, with nothing the user did to explain it.
    """
    sidebar.set_collapsed(True, animate=False)
    qapp.processEvents()
    sidebar.update_account_status(1, "syncing", "Downloading message list 40/200")
    qapp.processEvents()
    assert not sidebar._account_items[1]._status.isVisible()


def test_the_status_dot_returns_on_expanding(sidebar, qapp):
    sidebar.set_collapsed(True, animate=False)
    sidebar.update_account_status(1, "syncing", "Connecting")
    sidebar.set_collapsed(False, animate=False)
    qapp.processEvents()
    assert sidebar._account_items[1]._status.isVisible()


def test_the_unread_count_survives_collapsing_as_a_tooltip(sidebar):
    """There is no room for a count beside a hidden label, so it moves
    rather than simply vanishing."""
    sidebar.set_inbox_count(20)
    sidebar.set_collapsed(True, animate=False)
    assert "20" in sidebar._nav_buttons["inbox"].toolTip()
    sidebar.set_collapsed(False, animate=False)
    assert "20" in sidebar._nav_buttons["inbox"].text()


def test_collapsed_state_is_reported_once_per_change(sidebar):
    seen = []
    sidebar.collapsed_changed.connect(seen.append)
    sidebar.set_collapsed(True, animate=False)
    sidebar.set_collapsed(True, animate=False)   # already collapsed
    sidebar.set_collapsed(False, animate=False)
    assert seen == [True, False]


# --------------------------------------------------------------- grouping

def test_add_account_sits_with_the_accounts_not_with_settings(sidebar):
    """It used to be pinned to the bottom beside Settings, a few hundred
    pixels below the list it adds to, with an empty region between - two
    unrelated things adjacent, two related things apart."""
    layout = sidebar._accounts_layout
    widgets = [
        layout.itemAt(i).widget() for i in range(layout.count())
        if layout.itemAt(i).widget() is not None
    ]
    assert sidebar._add_btn in widgets, "Add account left the accounts group"
    # ...and it comes after the account rows, not before them.
    assert widgets.index(sidebar._add_btn) == len(widgets) - 1


def test_settings_stays_pinned_below_the_scroll_region(sidebar):
    root = sidebar._root
    last = root.itemAt(root.count() - 1).widget()
    assert last is sidebar._settings_btn


def test_an_account_with_nothing_unread_shows_no_badge(sidebar, qapp):
    """THE EMPTY-PILL BUG. set_collapsed forced the badge visible on
    expand, so every account with a zero count showed a small grey pill
    with nothing in it - the widget exists whatever the count is, and only
    the count gets to decide whether it is seen."""
    sidebar.set_collapsed(True, animate=False)
    sidebar.set_collapsed(False, animate=False)
    qapp.processEvents()
    assert sidebar._account_items[1]._badge.isVisible()   # has 3 unread
    assert not sidebar._account_items[2]._badge.isVisible()  # has 0


def test_the_badge_hides_when_the_count_drops_to_zero(sidebar, qapp):
    sidebar.update_unread_counts({1: 0, 2: 0, 3: 0})
    qapp.processEvents()
    for item in sidebar._account_items.values():
        assert not item._badge.isVisible()


def test_a_four_digit_count_does_not_widen_the_row(sidebar, qapp):
    sidebar.update_unread_counts({1: 4213, 2: 0, 3: 0})
    assert sidebar._account_items[1]._badge.text() == "99+"

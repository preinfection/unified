"""The account drawer: collapse behaviour, grouping, scope, and alignment.

Folder navigation, "Add account" and Settings moved to the dock
(tests/test_dock.py). What they guaranteed here moved with them; what is
left is asserted against the rows that remain - "All accounts" and one row
per account.

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
    """Left-aligned rows park their avatar off-centre once the label is
    gone, so the collapse control and the avatars each ended up on a
    slightly different line - the kind of misalignment that reads as
    sloppy without being nameable. The folder pills this used to measure
    are in the dock now; the rows that remain carry the same guarantee."""
    sidebar.set_collapsed(True, animate=False)
    qapp.processEvents()
    qapp.processEvents()

    def centre(widget) -> int:
        return widget.mapTo(sidebar, QPoint(0, 0)).x() + widget.width() // 2

    controls = [sidebar.collapse_btn]
    controls += [row._avatar for row in sidebar.rows()]
    centres = {centre(c) for c in controls}
    assert all(abs(c - RAIL_WIDTH // 2) <= 1 for c in centres), (
        f"rail controls are not aligned: {centres}"
    )


def test_collapsed_rows_keep_a_tooltip_and_an_accessible_name(sidebar):
    """A label-less control with no tooltip is a guess, and with no
    accessible name it is announced as "" out loud."""
    sidebar.set_collapsed(True, animate=False)
    for row in sidebar.rows():
        assert not row._email_label.isVisible()
        assert row.toolTip(), f"{row._email} has no tooltip when collapsed"
        assert row.accessibleName(), f"{row._email} has no accessible name"


def test_expanding_restores_every_label(sidebar, qapp):
    sidebar.set_collapsed(True, animate=False)
    sidebar.set_collapsed(False, animate=False)
    qapp.processEvents()
    for row in sidebar.rows():
        assert row._email_label.isVisible(), f"{row._email} lost its label"
        assert row.toolTip() == "", "an expanded row still carries a rail tooltip"
    assert sidebar._all_item._email_label.full_text() == "All accounts"


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
    rather than simply vanishing. (This guarded "Unified Inbox" when the
    folders lived here; the count on the dock's inbox is covered in
    test_dock.py, and the account rows keep the same promise.)"""
    sidebar.set_collapsed(True, animate=False)
    assert "3" in sidebar._account_items[1].toolTip()
    assert "15" in sidebar._all_item.toolTip(), "All accounts lost its total"
    sidebar.set_collapsed(False, animate=False)
    assert sidebar._account_items[1]._badge.text() == "3"
    assert "3 unread" in sidebar._account_items[1].accessibleName()


def test_collapsed_state_is_reported_once_per_change(sidebar):
    seen = []
    sidebar.collapsed_changed.connect(seen.append)
    sidebar.set_collapsed(True, animate=False)
    sidebar.set_collapsed(True, animate=False)   # already collapsed
    sidebar.set_collapsed(False, animate=False)
    assert seen == [True, False]


# --------------------------------------------------------------- grouping

def test_the_drawer_makes_no_offers_the_dock_already_makes(sidebar):
    """"Add account" used to sit under the account rows and Settings was
    pinned to the bottom. Both are in the dock now; a copy here as well
    would be a third "Add account" on the first screen anyone sees (the
    dock, the empty state and the drawer) - three competing offers."""
    from PySide6.QtWidgets import QAbstractButton

    names = {b.accessibleName() or b.text().strip()
             for b in sidebar.findChildren(QAbstractButton)}
    assert names == {"Collapse the sidebar"}, f"stray actions in the drawer: {names}"


def test_all_accounts_leads_the_list_and_sums_the_rows(sidebar):
    layout = sidebar._accounts_layout
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())
               if layout.itemAt(i).widget() is not None]
    rows = [w for w in widgets if w in sidebar.rows()]
    assert rows[0] is sidebar._all_item, "All accounts is not first"
    assert sidebar._all_item.unread() == 3 + 0 + 12


def test_exactly_one_row_is_ever_selected(sidebar):
    """The scope is one thing, so exactly one row shows it - including
    after a selection the drawer cannot honour."""
    assert sidebar.selected_rows() == [sidebar._all_item]
    sidebar.set_current_scope(2)
    assert [r.account_id for r in sidebar.selected_rows()] == [2]
    sidebar.set_current_scope(999)          # an account that is not here
    assert sidebar.selected_rows() == [sidebar._all_item]


def test_a_click_is_a_request_not_a_decision(sidebar):
    """Only the window decides what is current. A drawer that painted the
    click itself as well would be a second owner of the same state."""
    seen = []
    sidebar.scope_selected.connect(seen.append)
    sidebar._account_items[3].clicked.emit(3)
    assert seen == [3]
    assert sidebar.selected_rows() == [sidebar._all_item], (
        "the drawer changed its own selection without being told"
    )


def test_selection_is_not_frozen_into_an_inline_stylesheet(sidebar):
    """THE BUG. The selected surface was written into each row with
    setStyleSheet(f"...{t.BG_SELECTED}"), which fixed the dark palette's
    value into the widget - after switching to light the selected account
    kept a dark slab behind it. A property re-themes with the app."""
    sidebar.set_current_scope(1)
    for row in sidebar.rows():
        assert row.styleSheet() == "", f"{row._email} carries an inline stylesheet"
    assert sidebar._account_items[1].property("selected") == "true"


def test_no_accounts_says_so_instead_of_an_empty_region(qapp):
    motion.set_motion_enabled(False)
    bar = SidebarWidget()
    bar.set_accounts([], {})
    bar.show()
    qapp.processEvents()
    try:
        assert bar._empty_note.isVisible()
        assert not bar._all_item.isVisible(), "All accounts with no accounts"
    finally:
        bar.close()
        motion.set_motion_enabled(True)


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

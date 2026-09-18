"""Message-list geometry and the hover quick actions.

Both of these were broken in ways that are invisible in source and obvious
on screen, which is why they are asserted against measured geometry and
emitted signals rather than against the code that produces them.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from app.ui import theme as t
from app.ui.components.email_list import (
    ACTION_DELETE,
    ACTION_STAR,
    EmailListView,
)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _rows(count: int = 40) -> list[dict]:
    return [
        dict(
            id=i + 1, uid=str(i), account_id=1, folder="inbox",
            sender_name="Margaret Hamilton",
            sender_email="mhamilton@draper.io",
            subject="Re: guidance computer priority display and restart protocol",
            snippet=(
                "Agreed on the restart protocol. If the executive overflows we "
                "should drop the lowest priority job rather than halt."
            ),
            date_ts=1_900_000_000 - i * 60,
            is_read=i % 2, is_starred=0, has_attachments=0,
        )
        for i in range(count)
    ]


@pytest.fixture()
def view(qapp):
    v = EmailListView()
    v.resize(380, 600)
    v.set_rows(_rows())
    v.show()
    qapp.processEvents()
    yield v
    v.close()


# ------------------------------------------------------------- geometry

@pytest.mark.parametrize("width", [1200, 700, 460, 380, 320])
def test_rows_never_exceed_the_viewport_at_any_width(qapp, view, width):
    """THE CLIPPING BUG.

    sizeHint used to return option.rect.width(), which during a layout
    pass is the WIDGET width - so on a narrow window rows were laid out
    14px wider than the viewport the vertical scrollbar had left them.
    Every subject and snippet then elided against a width it did not have
    and was hard-clipped mid-word, with no ellipsis to show it had
    happened.
    """
    view.resize(width, 600)
    qapp.processEvents()
    viewport = view.viewport().width()
    for row in (1, 3, 5):
        rect = view.visualRect(view._model.index(row, 0))
        assert rect.width() <= viewport, (
            f"row {row} is {rect.width()}px in a {viewport}px viewport"
        )


@pytest.mark.parametrize("width", [1200, 700, 460, 380, 320])
def test_the_list_never_grows_a_horizontal_scrollbar(qapp, view, width):
    """Every line elides against its own width, so there is by
    construction nothing to the right to scroll to. A horizontal bar here
    only ever meant the rows were mis-sized, and it stole height from the
    list to show a control that could not help."""
    view.resize(width, 600)
    qapp.processEvents()
    assert not view.horizontalScrollBar().isVisible()


def test_compact_density_shortens_rows_without_losing_the_selection(qapp, view):
    view.select_email(3)
    comfortable = view.visualRect(view._model.index_of(3)).height()
    view.set_compact(True)
    qapp.processEvents()
    compact = view.visualRect(view._model.index_of(3)).height()
    assert compact < comfortable
    # A model reset would have dropped this; set_compact must not reset.
    assert view.selected_email_id() == 3


def test_date_headers_stay_shorter_than_messages(qapp, view):
    headers = [
        i for i, row in enumerate(view._model._rows) if row.get("is_header")
    ]
    assert headers, "no date group headers were inserted"
    header_h = view.visualRect(view._model.index(headers[0], 0)).height()
    assert header_h == t.ROW_GROUP_HEIGHT
    assert header_h < view._delegate.row_height()


# -------------------------------------------------------- quick actions

def _click(view, pos: QPoint) -> None:
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, pos,
        view.viewport().mapToGlobal(pos),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(event)


def _action_point(view, row: int, action: str) -> QPoint:
    rect = view.visualRect(view._model.index(row, 0)).adjusted(
        t.SPACE_SM, 1, -t.SPACE_SM, -1
    )
    return view._delegate.action_rects(rect)[action].center()


def test_hovering_a_row_reveals_its_quick_actions(qapp, view):
    row = next(
        i for i, r in enumerate(view._model._rows) if not r.get("is_header")
    )
    assert view._delegate.hover_row == -1
    view._delegate.hover_row = row
    boxes = view._delegate.action_rects(view.visualRect(view._model.index(row, 0)))
    assert set(boxes) == {ACTION_STAR, ACTION_DELETE}


def test_clicking_the_star_action_emits_and_does_not_change_selection(qapp, view):
    """Starring the fourth message must not throw away the message being
    read, so the click is consumed rather than falling through to the
    selection model."""
    rows = [i for i, r in enumerate(view._model._rows) if not r.get("is_header")]
    view.select_email(view._model._rows[rows[0]]["id"])
    selected_before = view.selected_email_id()

    target_row = rows[3]
    target_id = view._model._rows[target_row]["id"]
    view._delegate.hover_row = target_row

    seen = []
    view.star_toggled.connect(seen.append)
    _click(view, _action_point(view, target_row, ACTION_STAR))

    assert seen == [target_id]
    assert view.selected_email_id() == selected_before


def test_clicking_the_delete_action_emits_delete_not_star(qapp, view):
    rows = [i for i, r in enumerate(view._model._rows) if not r.get("is_header")]
    target_row = rows[2]
    target_id = view._model._rows[target_row]["id"]
    view._delegate.hover_row = target_row

    starred, deleted = [], []
    view.star_toggled.connect(starred.append)
    view.delete_requested.connect(deleted.append)
    _click(view, _action_point(view, target_row, ACTION_DELETE))

    assert deleted == [target_id]
    assert starred == []


def test_a_click_off_the_actions_still_selects_the_row(qapp, view):
    rows = [i for i, r in enumerate(view._model._rows) if not r.get("is_header")]
    target_row = rows[4]
    target_id = view._model._rows[target_row]["id"]
    rect = view.visualRect(view._model.index(target_row, 0))
    _click(view, QPoint(rect.left() + 120, rect.center().y()))
    assert view.selected_email_id() == target_id


# ------------------------------------------------------------ empty state

def test_a_wrapped_empty_state_detail_is_given_room_for_every_line(qapp):
    """THE OVERLAP BUG. QVBoxLayout gives an aligned child its sizeHint
    rather than stretching it, and a word-wrapped QLabel's sizeHint is its
    ONE-LINE height - so a detail that wrapped to two lines was allocated
    the height of one and rendered straight through the heading above it.
    """
    from app.ui.components.empty_state import EmptyState

    state = EmptyState()
    state.resize(700, 600)
    state.set_state(
        icon="search", title="No results",
        detail='Nothing in the local cache matches "zzzznothingmatches".',
    )
    state.show()
    qapp.processEvents()
    qapp.processEvents()

    title = state._title
    detail = state._detail
    # The wrapped detail really is more than one line here...
    assert detail.height() > detail.fontMetrics().height() * 1.4, (
        "the detail was allocated a single line's height"
    )
    # ...and it starts below the heading rather than through it.
    title_bottom = title.mapTo(state, title.rect().bottomLeft()).y()
    detail_top = detail.mapTo(state, detail.rect().topLeft()).y()
    assert detail_top >= title_bottom, "the detail overlaps the heading"
    state.close()


def test_an_empty_state_with_an_action_drops_the_icon(qapp):
    """"Add account" under a plus-in-a-circle says the same thing twice,
    and the glyph ends up below the button competing with it."""
    from app.ui.components.empty_state import EmptyState

    state = EmptyState()
    state.set_state(
        icon="add_circle", title="Nothing here yet", detail="Connect an account.",
        action_text="Add account", on_action=lambda: None,
    )
    assert not state._icon.isVisible()
    state.set_state(icon="inbox", title="Inbox is empty", detail="Nothing yet.")
    state.show()
    qapp.processEvents()
    assert state._icon.isVisible()
    state.close()

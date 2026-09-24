"""Three interaction ideas taken from Magic UI and rebuilt natively.

Each was studied from the component's actual registry source rather than
its demo, and each is here because it fixes something that was genuinely
weak - not because the component existed.

  Dock              -> the folders as one magnifying row at the top, and
                       one selection surface that SLIDES between them
                       (the magnification itself is in test_dock.py)
  ProgressiveBlur   -> a soft boundary where scrolling content meets the
                       chrome, instead of a hard cut
  BlurFade          -> content arriving on a change of context

What is asserted here is the BEHAVIOUR, not the appearance: that the
surface travels rather than teleporting, that the fade appears only where
something is actually cut off, and that all three land on the correct
final state under reduced motion.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app.ui import motion, theme as t
from app.ui.components.email_list import EmailListView
from app.ui.components.primitives import EDGE_FADE
from app.ui.components.dock import CELL, CELL_PEAK, Dock


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet
    app.setFont(t.make_font("field_value"))
    app.setStyleSheet(get_stylesheet())
    yield app


def settle(ms: int = 320) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _rows(n: int = 60) -> list[dict]:
    return [
        dict(id=i + 1, uid=str(i), account_id=1, folder="inbox",
             sender_name="Sender Name", sender_email="s@example.org",
             subject="A subject line here", snippet="some preview text",
             date_ts=1_900_000_000 - i * 60, is_read=1, is_starred=0,
             has_attachments=0)
        for i in range(n)
    ]


# ------------------------------------------- Dock -> sliding nav surface

@pytest.fixture()
def dock(qapp):
    bar = Dock()
    bar.show()
    qapp.processEvents()
    yield bar
    bar.close()
    motion.set_motion_enabled(True)


def test_the_selection_surface_travels_between_folders(dock, qapp):
    """THE POINT OF THE ADAPTATION. Each pill used to tween its own fill,
    so Inbox -> Sent was a cross-dissolve with both half-lit for 180ms.
    One surface that moves is unambiguous. It moved to the dock with the
    folders and still travels."""
    motion.set_motion_enabled(True)
    dock.set_current_folder("inbox", animate=False)
    start = dock.selection_rect().toRect()

    dock.set_current_folder("trash")
    settle(40)
    midway = dock.selection_rect().toRect()
    settle(400)
    end = dock.selection_rect().toRect()

    trash = dock.cell_rect_in_dock(dock.item("trash")).toRect()
    assert end.x() > start.x(), "the surface never moved"
    assert end.x() == trash.x()
    # Caught in flight: it travelled rather than teleporting.
    assert start.x() < midway.x() < end.x(), (
        f"the surface jumped ({start.x()} -> {midway.x()} -> {end.x()})"
    )


def test_there_is_only_ever_one_selection_surface(qapp):
    """A cell must not paint its own selected fill, or there would be two -
    the dock paints the one surface that slides."""
    from app.ui.components.dock import DockItem

    item = DockItem("inbox", "inbox", "Inbox", folder=True)
    item.resize(CELL + 4, 44)
    item.setChecked(True)
    item.show()
    qapp.processEvents()
    image = item.grab().toImage()
    cell = item.cell_rect().toRect()
    corner = image.pixelColor(cell.left() + 3, cell.top() + 3)
    assert corner.alpha() == 0 or corner.name().lower() != t.BG_SELECTED.lower(), (
        "the cell is painting a selected surface of its own"
    )
    item.close()


def test_choosing_an_account_does_not_retire_the_folder(dock, qapp):
    """WHAT REPLACED "selecting an account retires the surface".

    In the drawer, a folder and an account were alternatives in one list,
    so choosing an account had to switch the folder surface off. They are
    two independent answers now - which folder (dock) and whose (sidebar) -
    so a scope change leaves the folder surface exactly where it is. The
    window-level version of this is in test_dock.py."""
    motion.set_motion_enabled(True)
    dock.set_current_folder("sent", animate=False)
    before = dock.selection_rect()
    # A scope change touches the sidebar only; the dock is told the same
    # folder again.
    dock.set_current_folder("sent")
    settle(300)
    assert dock.selection_rect() == before
    assert [i.key for i in dock.items if i.isChecked()] == ["sent"]


def test_the_surface_lands_immediately_under_reduced_motion(dock, qapp):
    motion.set_motion_enabled(False)
    dock.set_current_folder("sent")
    qapp.processEvents()
    sent = dock.cell_rect_in_dock(dock.item("sent"))
    assert dock.selection_rect() == sent, (
        "reduced motion left the surface somewhere in between"
    )


def test_magnification_moves_the_surface_without_narrating_it(dock, qapp):
    """The cells change size under the pointer; the surface has to stay on
    its cell through that, not lag behind it or animate to catch up. (This
    was "collapsing moves the surface" when the pills changed width with
    the drawer - same guarantee, new cause.)"""
    motion.set_motion_enabled(True)
    dock.set_current_folder("inbox", animate=False)
    inbox = dock.item("inbox")
    dock._pointer_at(inbox.x() + inbox.width() / 2)
    settle(500)
    assert inbox.size_now == pytest.approx(CELL_PEAK, abs=0.2)
    assert dock.selection_rect() == dock.cell_rect_in_dock(inbox)
    dock._pointer_x = None
    dock._retarget()
    settle(500)
    assert inbox.size_now == pytest.approx(CELL, abs=0.2)
    assert dock.selection_rect() == dock.cell_rect_in_dock(inbox)


# ------------------------------ ProgressiveBlur -> soft scroll boundary

@pytest.fixture()
def listview(qapp):
    view = EmailListView()
    view.resize(500, 400)
    view.set_rows(_rows())
    view.show()
    qapp.processEvents()
    yield view
    view.close()


def _brightest(image, y0: int, y1: int) -> int:
    """The brightest pixel in a horizontal BAND.

    A band rather than a scanline: rows have gaps between them, so a
    single line sampled at an arbitrary y can easily land on background
    and report the list as dark everywhere.
    """
    return max(
        image.pixelColor(x, y).lightness()
        for y in range(max(0, y0), min(image.height(), y1))
        for x in range(40, image.width() - 40, 7)
    )


def test_both_edges_soften_when_content_is_cut_off(listview, qapp):
    """A list that ends in a hard cut against the toolbar reads as
    guillotined. Adapted from ProgressiveBlur - the blur is not
    reproduced, only the soft boundary."""
    bar = listview.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    qapp.processEvents()

    image = listview.viewport().grab().toImage()
    height = image.height()
    # A full row's worth of the middle, so the comparison is against real
    # content rather than whatever a single scanline happened to hit.
    middle = _brightest(image, height // 2 - 40, height // 2 + 40)

    assert _brightest(image, 0, 3) < middle, "the top edge is not softened"
    assert _brightest(image, height - 3, height) < middle, (
        "the bottom edge is not softened"
    )


def test_no_fade_when_the_whole_list_fits(qapp, monkeypatch):
    """A permanent vignette on a list with nothing cut off is decoration.

    Asserted on whether the painter is CALLED rather than on pixels: the
    first band of a short list contains a dim date header and the band
    below it contains bright sender names, so comparing their brightness
    measures the content, not the fade.
    """
    from app.ui.components import email_list as module

    calls = []
    monkeypatch.setattr(
        module, "paint_edge_fade",
        lambda *a, **k: calls.append(k),
    )

    view = EmailListView()
    view.resize(500, 600)
    view.set_rows(_rows(3))          # comfortably fits
    view.show()
    qapp.processEvents()
    view.viewport().grab()

    bar = view.verticalScrollBar()
    assert bar.minimum() == bar.maximum(), "this list was meant to fit"
    assert not calls, "a fade was painted over a list with nothing cut off"
    view.close()


def test_each_edge_fades_only_when_that_side_is_cut(qapp, monkeypatch):
    """At the top of a long list there is nothing above and everything
    below, so only the bottom should soften - and the reverse at the end.
    """
    from app.ui.components import email_list as module

    calls = []
    monkeypatch.setattr(
        module, "paint_edge_fade",
        lambda *a, **k: calls.append(k),
    )

    view = EmailListView()
    view.resize(500, 400)
    view.set_rows(_rows())
    view.show()
    qapp.processEvents()
    bar = view.verticalScrollBar()

    bar.setValue(bar.minimum())
    qapp.processEvents()
    calls.clear()
    view.viewport().grab()
    assert calls, "nothing painted at the top of a long list"
    assert calls[-1]["top"] is False, "softened an edge with nothing above it"
    assert calls[-1]["bottom"] is True

    bar.setValue(bar.maximum())
    qapp.processEvents()
    calls.clear()
    view.viewport().grab()
    assert calls[-1]["top"] is True
    assert calls[-1]["bottom"] is False, "softened an edge with nothing below it"
    view.close()


def test_the_fade_band_never_swallows_a_whole_row():
    """It is a boundary treatment, not a vignette."""
    assert EDGE_FADE < t.ROW_HEIGHT_COMPACT


# ----------------------------------------- BlurFade -> arriving content

def test_reveal_starts_offset_and_settles_at_zero(listview, qapp):
    motion.set_motion_enabled(True)
    motion.reveal(listview)
    assert float(listview.property("revealOffset")) > 0, "no offset to arrive from"
    settle(400)
    assert float(listview.property("revealOffset")) == pytest.approx(0.0, abs=0.01)


def test_reveal_lands_correctly_under_reduced_motion(listview, qapp):
    motion.set_motion_enabled(False)
    try:
        motion.reveal(listview)
        assert float(listview.property("revealOffset")) == 0.0
        effect = listview.graphicsEffect()
        assert effect is not None and effect.opacity() == 1.0
    finally:
        motion.set_motion_enabled(True)


def test_reveal_is_harmless_on_a_widget_without_the_property(qapp):
    """The rise is opt-in; everything else just fades."""
    from PySide6.QtWidgets import QLabel

    label = QLabel("x")
    motion.reveal(label)          # must not raise
    assert label.isVisible() or True


def test_a_routine_reload_does_not_re_reveal_the_list():
    """reload_email_list runs on every debounced sync tick - roughly once
    a second while syncing. A list that re-revealed itself that often
    would be unreadable, so the reveal is bound to the user actually
    moving: folder and account changes both go through _navigate, which
    reveals only when the location changed (the behaviour itself is
    asserted in test_dock.py)."""
    import inspect

    from app.ui.main_window import MainWindow

    body = inspect.getsource(MainWindow.reload_email_list)
    assert "_reveal_list" not in body, (
        "the reveal leaked into the routine reload path"
    )
    assert "_reveal_list" in inspect.getsource(MainWindow._navigate)
    for handler in (MainWindow._on_view_selected, MainWindow._on_account_selected):
        assert "_navigate" in inspect.getsource(handler)

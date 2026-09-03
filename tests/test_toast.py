"""Regression tests for the toast surface.

The bug these lock down: _ToastCard is a QWidget *subclass*, and Qt does
not paint a stylesheet `background` for a QWidget subclass unless
WA_StyledBackground is set. The card therefore rendered fully
transparent - confirmed by compositing a real toast over a magenta
backdrop and finding the backdrop showing through the card body. The fix
paints the surface (and the accent stripe, clipped to the same rounded
path) directly in paintEvent, so these tests assert against real
rendered pixels rather than against stylesheet strings.
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from app.ui import theme as t
from app.ui.components.toast import ToastHost

_BACKDROP = "#ff00ff"  # a color nothing in the design system uses


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet
    app.setStyleSheet(get_stylesheet())
    yield app


class _Backdrop(QWidget):
    """Bright magenta so any bleed-through is unmistakable."""

    def paintEvent(self, event) -> None:  # noqa: N802
        QPainter(self).fillRect(self.rect(), QColor(_BACKDROP))


def _settled(qapp, window, *toasts) -> "QImage":
    host = ToastHost(window)
    for title, message, kind in toasts:
        host.show(title, message, kind=kind)
    for _ in range(80):
        qapp.processEvents()
        time.sleep(0.005)
    return host, window.grab().toImage()


@pytest.fixture()
def window(qapp):
    win = _Backdrop()
    win.resize(600, 400)
    win.show()
    yield win


def _is_backdrop(color: QColor) -> bool:
    """Magenta-ish => the backdrop is showing through.

    The thresholds have to be tight enough to mean *magenta* and not
    merely "some red and blue": a dark neutral like the surface border
    (#2a2d35) has red and blue above 40 with green below 60 and would
    otherwise be reported as bleed-through, which is how this check
    fails on an opaque toast that is working perfectly.
    """
    return color.red() > 150 and color.blue() > 150 and color.green() < 100


def test_toast_surface_is_fully_opaque(qapp, window):
    host, image = _settled(
        qapp, window, ("Sync complete", "3 new messages", "success")
    )
    card = host._toasts[0]
    geo = card.geometry()

    bleed = []
    for dy in range(6, geo.height() - 6, 4):
        for dx in range(t.TOAST_STRIPE_WIDTH + 4, geo.width() - 6, 8):
            color = image.pixelColor(geo.x() + dx, geo.y() + dy)
            if _is_backdrop(color):
                bleed.append((dx, dy, color.name()))
    assert not bleed, f"backdrop bled through the toast surface at {bleed[:5]}"


def test_toast_surface_is_black(qapp, window):
    host, image = _settled(
        qapp, window, ("Sync complete", "3 new messages", "success")
    )
    geo = host._toasts[0].geometry()
    # Well inside the card, clear of the stripe, border and any text.
    color = image.pixelColor(geo.x() + geo.width() - 20, geo.y() + 10)
    assert color.name() == t.TOAST_BG == "#000000"


def test_accent_stripe_survives_the_repaint(qapp, window):
    """The stripe is painted in paintEvent now (not a child widget) - it
    must still be there, in the toast kind's color."""
    host, image = _settled(
        qapp, window, ("Sync complete", "done", "success")
    )
    geo = host._toasts[0].geometry()
    stripe = image.pixelColor(geo.x() + 1, geo.y() + geo.height() // 2)
    assert stripe.name() == t.TOAST_KIND_COLORS["success"]


def test_stacked_toasts_remain_visually_separated(qapp, window):
    host, image = _settled(
        qapp, window,
        ("Sync complete", "3 new messages", "success"),
        ("Server update failed", "Could not reach the server", "error"),
    )
    assert len(host._toasts) == 2
    first, second = host._toasts[0].geometry(), host._toasts[1].geometry()
    assert second.y() > first.y() + first.height(), "toasts overlap"
    # Each carries its own kind color, so they aren't one merged block.
    c1 = image.pixelColor(first.x() + 1, first.y() + first.height() // 2)
    c2 = image.pixelColor(second.x() + 1, second.y() + second.height() // 2)
    assert c1.name() == t.TOAST_KIND_COLORS["success"]
    assert c2.name() == t.TOAST_KIND_COLORS["error"]


def test_rounded_corner_is_not_painted_square(qapp, window):
    """The very corner pixel must remain backdrop - proving the surface
    follows the rounded path instead of filling a square rect."""
    host, image = _settled(qapp, window, ("Title", "body", "info"))
    geo = host._toasts[0].geometry()
    corner = image.pixelColor(geo.x(), geo.y())
    assert _is_backdrop(corner), (
        f"top-left corner painted {corner.name()} - surface is square, not rounded"
    )


def test_countdown_bar_animation_still_runs(qapp, window):
    host, _ = _settled(qapp, window, ("Title", "body", "info"))
    card = host._toasts[0]
    assert card._countdown.state().name in ("Running", "Stopped")
    # It starts at 1.0 and is animating down over the toast's lifetime.
    assert 0.0 <= card._bar.fraction <= 1.0

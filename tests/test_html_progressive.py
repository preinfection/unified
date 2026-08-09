"""Regression tests for the progressive-rendering behavior of the email
reader - specifically the layout stability that makes a promotional
email stop visibly reflowing while its images load.

Root cause these lock down: every remote <img> used to fall back to one
fixed 28x28 placeholder, so a 600x300 hero banner occupied a tiny square
at first paint and shoved the entire document down the page when it
arrived. Measured on a Gmail-promo-shaped fixture, that was a 287px
layout shift; reserving a correctly-shaped placeholder makes it 0px.
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QBuffer, QThreadPool
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.ui import html_view
from app.ui.html_view import (
    HtmlMailView,
    _reserved_image_placeholder,
    normalize_email_html,
)

# A Gmail-promotional-shaped email: hero banner plus a product grid, with
# every image remote (which is how real marketing mail is built).
_PRODUCTS = [(f"p{i}.jpg", 150, 150) for i in range(5)]
_PROMO_HTML = (
    '<body style="background:#ffffff;color:#222;">'
    '<div style="display:none">hidden preheader text</div>'
    '<img src="https://cdn.invalid/hero.jpg" width="600" height="300" alt="hero">'
    "<h1>Our Biggest Sale</h1>"
    "<table>"
    + "".join(
        f'<tr><td><img src="https://cdn.invalid/{n}" width="{w}" height="{h}"></td>'
        f"<td><h3>Product {i}</h3><p>Marketing copy.</p></td></tr>"
        for i, (n, w, h) in enumerate(_PRODUCTS)
    )
    + "</table></body>"
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet
    app.setStyleSheet(get_stylesheet())
    yield app


@pytest.fixture()
def view(qapp):
    widget = HtmlMailView()
    widget.setObjectName("emailBody")
    widget.resize(640, 900)
    widget.show()
    yield widget


def _render(qapp, view, html):
    view.set_email_html(html)
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(400):
        qapp.processEvents()
        if view._html:
            break
        time.sleep(0.002)
    for _ in range(10):
        qapp.processEvents()


def _doc_height(view) -> float:
    doc = view.document()
    doc.setTextWidth(view.viewport().width())
    return doc.size().height()


def _png(width: int, height: int) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#3366cc"))
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


def _deliver_all_images(qapp, view):
    view._on_image_fetched("https://cdn.invalid/hero.jpg", _png(600, 300))
    for name, w, h in _PRODUCTS:
        view._on_image_fetched(f"https://cdn.invalid/{name}", _png(w, h))
    for _ in range(60):
        qapp.processEvents()
        time.sleep(0.005)


# ------------------------------------------------------ reserved space

def test_declared_image_dimensions_are_captured_for_reservation():
    _html, boxes = normalize_email_html(_PROMO_HTML, max_width=600)
    assert boxes["https://cdn.invalid/hero.jpg"] == (600, 300)
    assert boxes["https://cdn.invalid/p0.jpg"] == (150, 150)


def test_reserved_placeholder_matches_the_declared_aspect_ratio():
    placeholder = _reserved_image_placeholder(600, 300)
    assert placeholder.width() / placeholder.height() == pytest.approx(2.0)


def test_layout_does_not_shift_when_remote_images_arrive(qapp, view):
    """The core guarantee: the document's laid-out height at first paint
    equals its height once every image has loaded."""
    _render(qapp, view, _PROMO_HTML)
    assert view._image_boxes, "declared dimensions should have been captured"
    height_before = _doc_height(view)

    _deliver_all_images(qapp, view)
    height_after = _doc_height(view)

    assert height_before == pytest.approx(height_after, abs=2.0), (
        f"layout shifted {abs(height_after - height_before):.0f}px while images loaded"
    )


def test_without_reserved_boxes_the_layout_does_shift(qapp, view):
    """Pins the actual cause: with the reservation removed (the old
    behavior), the same email demonstrably reflows. If this ever stops
    shifting, the test above has stopped proving anything."""
    _render(qapp, view, _PROMO_HTML)
    view._image_boxes = {}
    view.setHtml(view._html)
    for _ in range(10):
        qapp.processEvents()
    height_before = _doc_height(view)

    _deliver_all_images(qapp, view)
    height_after = _doc_height(view)

    assert abs(height_after - height_before) > 50, (
        "expected the un-reserved layout to visibly reflow"
    )


# --------------------------------------------------- first paint quality

def test_no_image_is_left_without_a_resource_at_first_paint(qapp, view):
    """Every <img> must resolve to a real QImage immediately - returning
    an empty QByteArray is what makes Qt draw its torn-page broken-image
    glyph, which is the 'ugly first paint' this fixes."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument

    _render(qapp, view, _PROMO_HTML)
    for src in view._image_boxes:
        resource = view.loadResource(
            QTextDocument.ResourceType.ImageResource.value, QUrl(src)
        )
        assert isinstance(resource, QImage) and not resource.isNull()


def test_hidden_preheader_is_absent_from_the_first_paint(qapp, view):
    _render(qapp, view, _PROMO_HTML)
    assert "hidden preheader text" not in view.document().toPlainText()


def test_promotional_email_keeps_its_own_light_background(qapp, view):
    _render(qapp, view, _PROMO_HTML)
    color = view.grab().toImage().pixelColor(300, 400)
    assert color.name() == "#ffffff"


# ------------------------------------------- no full reparse per image

def test_image_arrival_does_not_reparse_the_document(qapp, view, monkeypatch):
    """setHtml() re-runs Qt's whole HTML parser. An image arriving must
    trigger a relayout (markContentsDirty), never a reparse - otherwise a
    20-image newsletter reparses a 100KB document 20 times."""
    _render(qapp, view, _PROMO_HTML)

    calls = []
    original = HtmlMailView.setHtml
    monkeypatch.setattr(HtmlMailView, "setHtml",
                        lambda self, html: calls.append(html) or original(self, html))

    _deliver_all_images(qapp, view)
    assert not calls, f"document was reparsed {len(calls)}x while images arrived"

"""Widget-level regression tests for HtmlMailView: confirms the app's own
dark theme never bleeds into email content, while still applying a
sensible default (not the app's palette) for HTML that doesn't declare
its own colors. Runs headless (QT_QPA_PLATFORM=offscreen).
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from app.ui import html_view
from app.ui import theme as t


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    # Without the real app-wide stylesheet applied, HtmlMailView's
    # setStyleSheet("") "reset to app default" has nothing to fall back
    # to and shows Qt's own bare widget default (white) instead of the
    # app's dark panel color - matching the real app, which always
    # applies this before any window is built, is required for these
    # tests to observe real behavior rather than a test-only artifact.
    from app.ui.style import get_stylesheet
    app.setStyleSheet(get_stylesheet())
    yield app


@pytest.fixture()
def view(qapp):
    from app.ui.html_view import HtmlMailView
    widget = HtmlMailView()
    widget.setObjectName("emailBody")
    widget.resize(400, 300)
    widget.show()
    yield widget


class _CapturingThreadPool:
    """Stands in for QThreadPool.globalInstance(): captures a submitted
    QRunnable instead of running it on a real worker thread, so a test
    can observe the state *between* "normalize dispatched" and "normalize
    delivered" deterministically instead of racing a real background
    thread (which, for a tiny fixture, can finish before the test's next
    line runs)."""

    def __init__(self):
        self.tasks = []

    def start(self, task) -> None:
        self.tasks.append(task)

    def run_all(self) -> None:
        for task in self.tasks:
            task.run()  # runs synchronously on this (the test/GUI) thread,
        self.tasks.clear()  # so its done.emit() is delivered immediately


@pytest.fixture()
def capturing_pool(monkeypatch):
    pool = _CapturingThreadPool()
    monkeypatch.setattr(html_view.QThreadPool, "globalInstance", lambda: pool)
    # Remote-image fetches use their own dedicated pool (see
    # _image_fetch_pool), not QThreadPool.globalInstance() - redirect
    # that too so a test never opens a real network connection.
    monkeypatch.setattr(html_view, "_image_fetch_pool", lambda: pool)
    return pool


def _render_and_sample(qapp, view, html: str, x: int = 60, y: int = 60):
    view.set_email_html(html)
    QThreadPool.globalInstance().waitForDone(3000)
    for _ in range(200):
        qapp.processEvents()
        if view._html:
            break
        time.sleep(0.005)
    for _ in range(10):
        qapp.processEvents()
    image = view.grab().toImage()
    return image.pixelColor(x, y)


def test_loading_placeholder_uses_app_theme_not_email_content_theme(view, capturing_pool):
    """Before the (deliberately not-yet-run) background normalize task
    delivers real HTML, the pane shows an app status message ("Rendering
    message...") - that's app UI, not email content, and must stay on the
    app's own dark palette."""
    view.set_email_html("<p>irrelevant - not run yet</p>")
    color = view.grab().toImage().pixelColor(60, 60)
    assert color.name() == t.BG_PANEL, (
        f"loading placeholder should use the app's dark panel color "
        f"({t.BG_PANEL}), got {color.name()}"
    )
    # Now let the captured task actually run/deliver - only then should
    # the neutral light content theme take over.
    capturing_pool.run_all()
    color2 = view.grab().toImage().pixelColor(60, 60)
    assert color2.name() == "#ffffff"


def test_html_with_no_declared_colors_gets_a_neutral_light_default(qapp, view):
    """An email that declares no background/color of its own must NOT
    inherit the app's dark palette - every real email client falls back
    to a neutral (light) default for unstyled mail, not its own chrome
    theme."""
    color = _render_and_sample(qapp, view, "<p>Plain email, no styling at all.</p>")
    assert color.name() == "#ffffff"
    assert color.name() != t.BG_PANEL


def test_explicit_light_email_theme_is_preserved(qapp, view):
    color = _render_and_sample(
        qapp, view,
        '<body style="background:#ffffff;color:#111111;">'
        '<p>Explicit light theme.</p></body>',
    )
    assert color.name() == "#ffffff"


def test_explicit_dark_email_theme_is_preserved_not_forced_to_app_palette(qapp, view):
    """The core of this requirement: an email that is ALREADY dark-themed
    must render with *its own* dark color, not get remapped onto the
    app's dark palette (which would be a coincidental-looking but wrong
    behavior) and must never get forced light either."""
    color = _render_and_sample(
        qapp, view,
        '<body style="background:#0a0a0a;color:#f5f5f5;">'
        '<p>Intentionally dark email.</p></body>',
    )
    assert color.name() == "#0a0a0a"
    assert color.name() != t.BG_PANEL, "must be the EMAIL's own dark color, not the app's"


def test_unfetched_remote_image_gets_a_neutral_placeholder_not_a_broken_icon(view, capturing_pool):
    """Confirmed by direct rendering: Qt's own default for an unresolved
    ImageResource is a "broken document" glyph that reads as an error,
    not "still loading". loadResource() must hand back a real placeholder
    QImage instead of an empty QByteArray (which is what triggers Qt's
    own broken-image glyph). Uses the capturing (non-executing) thread
    pool so this never actually opens a real network connection.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QImage

    # Remote images are withheld until the user opts in (see the privacy
    # tests below); this test is about the placeholder, so opt in first.
    view.set_remote_images_allowed(True)
    resource = view.loadResource(
        QTextDocument.ResourceType.ImageResource.value,
        QUrl("https://nonexistent.invalid/pic.png"),
    )
    assert isinstance(resource, QImage)
    assert not resource.isNull()
    assert resource.width() > 0 and resource.height() > 0
    # The fetch was dispatched to the (non-executing, test-only) pool -
    # not run for real, so no actual network connection was attempted.
    assert len(capturing_pool.tasks) == 1


def test_image_fetch_pool_is_bounded_and_separate_from_normalize_pool(qapp):
    """Remote-image fetches must not share the CPU-sized global thread
    pool with HTML normalization work, and must have an explicit,
    reasonable concurrency cap rather than an implicit one."""
    fetch_pool = html_view._image_fetch_pool()
    assert fetch_pool is not QThreadPool.globalInstance()
    assert fetch_pool.maxThreadCount() == html_view._MAX_CONCURRENT_IMAGE_FETCHES
    assert 0 < fetch_pool.maxThreadCount() <= 12


def test_switching_from_html_email_back_to_plain_text_restores_app_theme(qapp, view):
    """set_email_text (loading states, plain-text bodies) must not be
    left showing the neutral light theme from a previously displayed HTML
    email."""
    _render_and_sample(qapp, view, '<body style="background:#ffffff;"><p>hi</p></body>')
    view.set_email_text("Plain text body, no HTML.")
    color = view.grab().toImage().pixelColor(60, 60)
    assert color.name() == t.BG_PANEL

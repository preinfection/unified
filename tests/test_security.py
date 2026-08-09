"""Security regression tests for the v1.2.1 hardening pass.

Each test corresponds to a confirmed finding or to a boundary that was
audited and found already sound - so a future refactor that quietly
removes one of these protections fails here rather than in the wild.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QApplication

from app.database import Database
from app.ui import html_view
from app.ui.html_view import _SAFE_LINK_SCHEMES, HtmlMailView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def view(qapp, monkeypatch):
    opened: list[str] = []
    # Never actually hand a URL to the OS during tests.
    monkeypatch.setattr(html_view.QDesktopServices, "openUrl",
                        lambda url: opened.append(url.toString()) or True)
    widget = HtmlMailView()
    widget.setObjectName("emailBody")
    widget.resize(400, 300)
    widget._opened = opened
    yield widget


# ===================================================================
# FINDING 1 (HIGH): unsafe link schemes handed to the OS shell.
# setOpenExternalLinks(True) routes every anchor to
# QDesktopServices.openUrl(), which on Windows is ShellExecute. A
# malicious email could link to a local executable, or to a UNC path
# that leaks the user's NTLM hash to an attacker-controlled SMB server.
# ===================================================================

@pytest.mark.parametrize("url", [
    "file:///C:/Windows/System32/calc.exe",   # local program execution
    "file://attacker.example.com/share/x",    # NTLM hash leak over SMB
    "smb://attacker.example.com/share",
    "javascript:alert(1)",
    "ms-msdt:/id PCWDiagnostic",              # Follina-style protocol abuse
    "search-ms:query=x&crumb=location:\\\\attacker",
    "vbscript:msgbox(1)",
    "data:text/html,<script>alert(1)</script>",
])
def test_unsafe_link_schemes_are_never_opened(view, url):
    view._on_anchor_clicked(QUrl(url))
    assert view._opened == [], f"{url} was handed to the OS handler"


@pytest.mark.parametrize("url", [
    "https://example.com/offer",
    "http://example.com/offer",
    "mailto:someone@example.com",
])
def test_safe_link_schemes_still_open(view, url):
    view._on_anchor_clicked(QUrl(url))
    assert view._opened == [url]


def test_qt_is_not_allowed_to_open_links_by_itself(view):
    """Qt must not be left to route anchors on its own - that path has no
    scheme filtering at all."""
    assert view.openExternalLinks() is False


def test_scheme_allowlist_is_closed_not_a_denylist():
    """A denylist would miss the next shell-registered protocol; this must
    stay an explicit allowlist of three."""
    assert _SAFE_LINK_SCHEMES == frozenset({"http", "https", "mailto"})


# ===================================================================
# FINDING 2 (MEDIUM): remote images loaded automatically.
# Every tracking pixel became a silent read receipt, and an email could
# make the client issue requests to hosts only this machine can reach
# (192.168.x.x, 127.0.0.1, 169.254.169.254 cloud metadata) - blind SSRF
# and internal port discovery via load success/failure.
# ===================================================================

def test_remote_images_are_blocked_by_default(view, monkeypatch):
    dispatched = []
    monkeypatch.setattr(html_view, "_image_fetch_pool",
                        lambda: type("P", (), {"start": lambda s, t: dispatched.append(t)})())
    view.loadResource(QTextDocument.ResourceType.ImageResource.value,
                      QUrl("https://tracker.example.com/pixel.gif"))
    assert dispatched == [], "a remote image was fetched without consent"
    assert view.has_blocked_remote_images()


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8080/admin",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]:9200/",
])
def test_internal_hosts_are_not_probed_by_default(view, monkeypatch, url):
    dispatched = []
    monkeypatch.setattr(html_view, "_image_fetch_pool",
                        lambda: type("P", (), {"start": lambda s, t: dispatched.append(t)})())
    view.loadResource(QTextDocument.ResourceType.ImageResource.value, QUrl(url))
    assert dispatched == []


def test_blocked_image_still_gets_a_placeholder_not_a_broken_icon(view):
    resource = view.loadResource(
        QTextDocument.ResourceType.ImageResource.value,
        QUrl("https://tracker.example.com/pixel.gif"),
    )
    assert isinstance(resource, QImage) and not resource.isNull()


def test_image_consent_does_not_leak_between_messages(view):
    view.set_remote_images_allowed(True)
    assert view._allow_remote_images is True
    view.set_email_html("<p>a different sender's message</p>")
    assert view._allow_remote_images is False, "consent leaked to the next email"


def test_non_http_image_schemes_are_never_fetched(view, monkeypatch):
    """cid: is resolved during MIME parsing and data: is decoded inline;
    nothing else should ever reach the network layer."""
    dispatched = []
    monkeypatch.setattr(html_view, "_image_fetch_pool",
                        lambda: type("P", (), {"start": lambda s, t: dispatched.append(t)})())
    view.set_remote_images_allowed(True)
    for url in ("file:///C:/Windows/win.ini", "ftp://example.com/x.png"):
        view.loadResource(QTextDocument.ResourceType.ImageResource.value, QUrl(url))
    assert dispatched == []


# ===================================================================
# AUDITED AND ALREADY SOUND - pinned so they stay that way.
# ===================================================================

def test_search_is_parameterised_against_sql_injection(tmp_path):
    db = Database(tmp_path / "m.db")
    aid = db.add_account("a@example.com", "gmail")
    db.upsert_email(dict(
        account_id=aid, uid="1", folder="inbox", sender_name="A",
        sender_email="a@example.com", subject="hello", snippet="",
        body_text="", body_html="", date_ts=1, is_read=0, is_starred=0,
        has_attachments=0, body_fetched=1,
    ))
    # A classic injection payload must be treated as a literal string.
    hostile = "'; DROP TABLE emails; --"
    assert db.list_emails("inbox", search=hostile) == []
    # The table is still there and the row survived.
    assert db.count_emails("inbox") == 1
    db.close()


def test_scripts_and_handlers_cannot_execute_in_the_reader(qapp, view):
    """QTextBrowser has no script engine at all, so <script> and on*
    handlers are inert. This pins that the reader is never swapped for
    something that does execute (e.g. QWebEngineView) without a
    deliberate security review."""
    from PySide6.QtWidgets import QTextBrowser
    assert isinstance(view, QTextBrowser)
    view.setHtml("<script>window.x=1</script><img src=x onerror='window.y=1'>"
                 "<p>body</p>")
    # Script text must not be rendered as visible content either.
    assert "window.x" not in view.document().toPlainText()


def test_oversized_and_malformed_html_does_not_raise(qapp):
    """Hostile input must degrade, never crash the reader."""
    from app.ui.html_view import normalize_email_html
    for hostile in (
        "<img " * 5000,                      # unterminated tag flood
        "<div style='display:none'>" * 2000,  # deep nesting
        "<img src='" + "A" * 200_000 + "'>",  # oversized attribute
        "\x00\xff<p>nul bytes</p>",
        "<style>" + "a{background:url(x)}" * 5000 + "</style>",
    ):
        html, boxes = normalize_email_html(hostile, max_width=560)
        assert isinstance(html, str) and isinstance(boxes, dict)


def test_image_fetch_has_a_size_cap_and_timeout():
    """An email must not be able to hang a worker forever or exhaust
    memory through an enormous image."""
    assert html_view._MAX_IMAGE_BYTES <= 16 * 1024 * 1024
    assert 0 < html_view._FETCH_TIMEOUT <= 30


def test_data_uri_decoder_rejects_non_base64_and_garbage(qapp):
    """Malformed data: URIs must return None, not raise or produce a
    partially-decoded image."""
    assert HtmlMailView._decode_data_uri(QUrl("data:image/png,notbase64")) is None
    assert HtmlMailView._decode_data_uri(QUrl("data:image/png;base64,!!!!")) is None

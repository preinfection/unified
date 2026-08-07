"""Email body viewer: QTextBrowser that also loads remote (http/https) images.

QTextBrowser cannot fetch network resources on its own, which is why HTML
newsletters look broken out of the box. This subclass downloads referenced
images on background threads, caches them, and re-renders when they arrive.
Downloads are size-capped and failures fall back to the plain placeholder.
"""

from __future__ import annotations

import logging
import threading
import urllib.request

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QTextBrowser

log = logging.getLogger(__name__)

_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_FETCH_TIMEOUT = 10


class _ImageBridge(QObject):
    """Delivers downloaded bytes from worker threads to the UI thread."""

    fetched = Signal(str, bytes)


class HtmlMailView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self._html = ""
        self._images: dict[str, QByteArray] = {}
        self._pending: set[str] = set()
        self._bridge = _ImageBridge()
        self._bridge.fetched.connect(self._on_image_fetched)
        # Coalesce re-renders when many images arrive close together.
        self._rerender_timer = QTimer(self)
        self._rerender_timer.setSingleShot(True)
        self._rerender_timer.setInterval(150)
        self._rerender_timer.timeout.connect(self._rerender)

    # ------------------------------------------------------------------ public

    def set_email_html(self, html: str) -> None:
        self._html = html
        self._pending.clear()
        self.setHtml(html)

    def set_email_text(self, text: str) -> None:
        self._html = ""
        self._pending.clear()
        self.setPlainText(text)

    # -------------------------------------------------------------- resources

    def loadResource(self, rtype: int, url: QUrl):
        if rtype == QTextDocument.ResourceType.ImageResource.value:
            key = url.toString()
            if key in self._images:
                return self._images[key]
            if url.scheme() in ("http", "https") and key not in self._pending:
                self._pending.add(key)
                threading.Thread(
                    target=self._fetch, args=(key,), daemon=True
                ).start()
            # Nothing yet: QTextBrowser shows its small placeholder.
            return QByteArray()
        return super().loadResource(rtype, url)

    def _fetch(self, url: str) -> None:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Unified/1.0"}
            )
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
                data = resp.read(_MAX_IMAGE_BYTES + 1)
            if len(data) > _MAX_IMAGE_BYTES:
                log.info("Image too large, skipped: %s", url)
                return
            self._bridge.fetched.emit(url, data)
        except Exception as e:
            log.debug("Image fetch failed (%s): %s", url, e)

    def _on_image_fetched(self, url: str, data: bytes) -> None:
        self._images[url] = QByteArray(data)
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(url), self._images[url]
        )
        if self._html:
            self._rerender_timer.start()

    def _rerender(self) -> None:
        """Re-set the HTML so newly arrived images get laid out, keeping scroll."""
        bar = self.verticalScrollBar()
        pos = bar.value()
        self.setHtml(self._html)
        bar.setValue(pos)

"""Email body viewer: QTextBrowser that also loads remote (http/https) and
inline (data:) images, and defends against QTextDocument's real HTML
rendering limitations.

Two limitations in particular corrupt real-world newsletter/marketing
HTML, confirmed by direct testing (not assumed) against fixtures matching
common template patterns:

1. QTextDocument ignores CSS `max-width`/`height:auto` entirely. An
   image with no HTML width/height attribute renders at its raw native
   pixel size, which - for a 1200px-wide banner in a ~600px reading pane
   - simply overflows the viewport. This is the single most common
   responsive-image pattern in real email templates, so ignoring it is
   not a corner case.
2. When an `<img>` tag's width/height *attributes* don't match the
   image's real aspect ratio (extremely common: retina-2x source assets,
   template edits that changed the image but not the markup), Qt's
   scaling does not cleanly stretch or letterbox the way a browser does
   - it drops rows of the source image and redistributes what's left,
   which is exactly the "sliced into strips / displaced content" symptom
   this class was rewritten to fix. Confirmed by rendering a labeled
   test image at a deliberately mismatched width/height and observing
   entire labeled bands vanish.

Both are QTextDocument engine limitations, not something more CSS can
paper over. The fix normalizes every <img> tag before handing HTML to
the document (strip height and width/height CSS, cap any declared
width), and separately caps the actual pixel data returned for each
image to the viewport width - confirmed by testing that Qt scales
correctly when given a width-only, aspect-consistent target.
"""

from __future__ import annotations

import base64
import binascii
import logging
import threading
import urllib.request
from html.parser import HTMLParser

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal, Qt
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QTextBrowser

from app.ui import theme as t

log = logging.getLogger(__name__)

_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_FETCH_TIMEOUT = 10
_DEFAULT_MAX_WIDTH = 560  # used before the widget has a real viewport size
_SIZE_STYLE_PROPS = ("width", "max-width", "min-width", "height", "max-height", "min-height")


def _strip_size_styles(style: str) -> str:
    """Remove width/height-family declarations from an inline style
    attribute, keeping everything else (display, margin, border-radius,
    ...) intact."""
    if not style:
        return style
    kept = []
    for decl in style.split(";"):
        decl = decl.strip()
        if not decl:
            continue
        prop = decl.split(":", 1)[0].strip().lower()
        if prop not in _SIZE_STYLE_PROPS:
            kept.append(decl)
    return "; ".join(kept)


class _ImgSizeNormalizer(HTMLParser):
    """Rewrites every <img> tag so QTextDocument gets a width-only sizing
    hint (never a mismatched height, never a CSS width/height it silently
    ignores or mishandles) - see module docstring for why.

    Everything other than <img> tags passes through byte-for-byte via
    get_starttag_text()/original data, so this never risks corrupting
    the rest of a real newsletter's markup.
    """

    def __init__(self, max_width: int):
        super().__init__(convert_charrefs=False)
        self.max_width = max_width
        self.out: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            self.out.append(self.get_starttag_text() or "")
            return
        self._emit_img(attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            self.out.append(self.get_starttag_text() or "")
            return
        self._emit_img(attrs, self_closing=True)

    def _emit_img(self, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> None:
        result: dict[str, str] = {}
        declared_width: int | None = None
        for name, value in attrs:
            key = name.lower()
            value = value or ""
            if key == "width":
                try:
                    declared_width = int(float(value.strip().rstrip("px")))
                except ValueError:
                    declared_width = None
                continue
            if key == "height":
                continue  # always dropped - see module docstring
            if key == "style":
                cleaned = _strip_size_styles(value)
                if cleaned:
                    result["style"] = cleaned
                continue
            result[name] = value

        if declared_width and declared_width > 0:
            result["width"] = str(min(declared_width, self.max_width))
        # No declared width: left unset here: an oversized-but-undeclared
        # image is instead caught by the pixel-level cap in
        # HtmlMailView._on_image_fetched, since only the actual decoded
        # image data reveals whether it needs capping.

        pieces = [f'{k}="{v}"' for k, v in result.items()]
        tag_str = "<img " + " ".join(pieces) + (" />" if self_closing else ">")
        self.out.append(tag_str)

    def handle_data(self, data: str) -> None:
        self.out.append(data)

    def handle_entityref(self, name: str) -> None:
        self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.out.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.out.append(f"<!{decl}>")

    def unknown_decl(self, data: str) -> None:
        self.out.append(f"<![{data}]>")

    def handle_endtag(self, tag: str) -> None:
        self.out.append(f"</{tag}>")

    def handle_pi(self, data: str) -> None:
        self.out.append(f"<?{data}>")


def normalize_image_sizing(html: str, max_width: int) -> str:
    """Best-effort <img> tag normalization; falls back to the original
    HTML unchanged if parsing hits something unexpected rather than
    ever risking showing nothing."""
    if not html or "<img" not in html.lower():
        return html
    try:
        parser = _ImgSizeNormalizer(max_width)
        parser.feed(html)
        parser.close()
        return "".join(parser.out)
    except Exception as e:
        log.debug("Image-sizing normalization skipped (%s)", e)
        return html


class _ImageBridge(QObject):
    """Delivers downloaded bytes from worker threads to the UI thread."""

    fetched = Signal(str, bytes)


class HtmlMailView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        # Only takes effect for plain-text bodies - real HTML mail carries
        # its own fonts, which this deliberately never overrides.
        self.setFont(t.make_font("body"))
        self._html = ""
        self._images: dict[str, QImage] = {}
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
        self._images.clear()  # previous message's decoded images are done
        self._html = normalize_image_sizing(html, self._max_width())
        self._pending.clear()
        self.setHtml(self._html)

    def set_email_text(self, text: str) -> None:
        self._images.clear()
        self._html = ""
        self._pending.clear()
        self.setPlainText(text)

    def _max_width(self) -> int:
        # Some margin off the actual viewport so an image never touches
        # the scrollbar edge; falls back to a sane default before the
        # widget has been laid out with a real size yet.
        vw = self.viewport().width()
        return max(vw - 24, 200) if vw > 24 else _DEFAULT_MAX_WIDTH

    # -------------------------------------------------------------- resources

    def loadResource(self, rtype: int, url: QUrl):
        if rtype == QTextDocument.ResourceType.ImageResource.value:
            key = url.toString()
            if key in self._images:
                return self._images[key]
            if url.scheme() == "data":
                image = self._decode_data_uri(url)
                if image is not None:
                    self._images[key] = image
                    return image
                return QByteArray()
            if url.scheme() in ("http", "https") and key not in self._pending:
                self._pending.add(key)
                threading.Thread(
                    target=self._fetch, args=(key,), daemon=True
                ).start()
            # Nothing yet: QTextBrowser shows its small placeholder.
            return QByteArray()
        return super().loadResource(rtype, url)

    @staticmethod
    def _decode_data_uri(url: QUrl) -> QImage | None:
        # QTextDocument does not resolve data: URIs on its own - confirmed
        # by direct testing, not assumed - so this is fully manual.
        try:
            path = url.toString()
            header, _, payload = path.partition(",")
            if ";base64" not in header:
                return None
            raw = base64.b64decode(payload)
        except (ValueError, binascii.Error) as e:
            log.debug("Bad data: URI image (%s)", e)
            return None
        image = QImage.fromData(raw)
        return image if not image.isNull() else None

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
        image = QImage.fromData(data)
        if image.isNull():
            return
        # Pixel-level backstop: caps images QTextDocument never got a
        # sizing hint for at all (no width attribute, no matching CSS),
        # which normalize_image_sizing can't catch since it never sees
        # the real pixel dimensions - only the fetched bytes reveal that.
        max_width = self._max_width()
        if image.width() > max_width:
            image = image.scaledToWidth(
                max_width, Qt.TransformationMode.SmoothTransformation
            )
        self._images[url] = image
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(url), image
        )
        if self._html:
            self._rerender_timer.start()

    def _rerender(self) -> None:
        """Re-set the HTML so newly arrived images get laid out, keeping scroll."""
        bar = self.verticalScrollBar()
        pos = bar.value()
        self.setHtml(self._html)
        bar.setValue(pos)

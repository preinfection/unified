"""Email body viewer: QTextBrowser that also loads remote (http/https) and
inline (data:) images, and defends against QTextDocument's real HTML
rendering limitations.

Confirmed by direct testing against fixtures matching real marketing-email
templates (not assumed - see tests/test_html_rendering.py), QTextDocument's
HTML/CSS engine corrupts real-world promotional HTML in four distinct ways:

1. Ignores CSS `max-width`/`height:auto` entirely. An image with no HTML
   width/height attribute renders at its raw native pixel size, which -
   for a 1200px-wide banner in a ~600px reading pane - simply overflows
   the viewport. The single most common responsive-image pattern in real
   email templates, not a corner case.
2. When an `<img>` tag's width/height *attributes* don't match the
   image's real aspect ratio (retina-2x source assets, template edits
   that changed the image but not the markup), Qt's scaling drops rows
   of the source image and redistributes what's left instead of
   stretching or letterboxing - the "sliced into strips / displaced
   content" symptom. Confirmed by rendering a labeled test image at a
   deliberately mismatched width/height and observing entire labeled
   bands vanish.
3. Does not support CSS `background-image` at all, on any element -
   confirmed by rendering a real promotional-email fixture (hero banner
   + button background via `background-image`, both dropped) and
   inspecting QTextDocument's resulting image resources directly: zero
   of them were picked up. Hero banners and button-background graphics -
   extremely common in marketing HTML - simply never appear.
4. Does not honor `display:none`. The "hidden preheader" trick nearly
   every marketing ESP uses (invisible preview text stuffed at the top
   of the HTML body, meant to only show up in the inbox preview line)
   is real, visible-to-QTextDocument text, so it was rendering as the
   first, out-of-place line of every promotional email. Confirmed by
   rendering the same fixture and finding the "hidden" text present in
   the laid-out document's plain text.

None of these are something more CSS can paper over - they are engine
limitations. The fix is a normalization pass over the raw HTML before it
reaches QTextDocument: image tags get a width-only sizing hint (never a
mismatched height, never a CSS width/height Qt silently ignores or
mishandles); `display:none` elements (by inline style or by a class
matched against a <style> block rule) are dropped entirely, tag and
content; `background-image` (inline or class-based) is rewritten to the
legacy `background=` HTML attribute on elements Qt does support it on
(table/td/th/tr/body), or as a fallback a synthetic <img> child on
anything else, so the image is visible even where the fix can't be
pixel-perfect. Actual pixel data returned for each image is separately
capped to the viewport width - confirmed by testing that Qt scales
correctly when given a width-only, aspect-consistent target.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
import urllib.request
from functools import lru_cache
from html.parser import HTMLParser

from PySide6.QtCore import QByteArray, QObject, QThreadPool, QRunnable, QTimer, QUrl, Signal, Qt
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QTextDocument
from PySide6.QtWidgets import QTextBrowser

from app.ui import theme as t

log = logging.getLogger(__name__)

_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_FETCH_TIMEOUT = 10
_DEFAULT_MAX_WIDTH = 560  # used before the widget has a real viewport size
_SIZE_STYLE_PROPS = ("width", "max-width", "min-width", "height", "max-height", "min-height")
_SIZE_ATTR_STRIP = ("srcset", "sizes")  # responsive-image hints Qt can't use

# A url(...) reference inside a background/background-image declaration -
# deliberately requires "url(" so it never matches background-color/
# background-position/etc, only the property this file can actually act on.
_BG_URL_RE = re.compile(
    r'background(?:-image)?\s*:\s*url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)', re.IGNORECASE
)
_DISPLAY_NONE_RE = re.compile(r'display\s*:\s*none', re.IGNORECASE)
_STYLE_BLOCK_RE = re.compile(r'<style[^>]*>(.*?)</style>', re.IGNORECASE | re.DOTALL)
_CLASS_RULE_RE = re.compile(r'\.([a-zA-Z0-9_,\-\s.]+?)\s*\{([^}]*)\}')
# Cheap pre-check so plain-text-ish HTML (no images, nothing hidden, no
# background-image) skips the parser entirely instead of paying its cost.
_NEEDS_NORMALIZATION = re.compile(r'<img|display\s*:\s*none|background(?:-image)?\s*:', re.IGNORECASE)

# Elements Qt's rich-text engine natively honors the legacy "background"
# HTML attribute on (a real, if old-school, way to show a background
# image) - everything else gets a synthetic <img> instead, since Qt has
# no other way at all to show a CSS background-image.
_BACKGROUND_ATTR_TAGS = {"table", "td", "th", "tr", "body"}


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


def _extract_style_block_maps(html: str) -> tuple[set[str], dict[str, str]]:
    """Best-effort scan of <style> blocks for two patterns real marketing
    templates lean on that QTextDocument does not implement itself:
    class-based `display:none` (the hidden-preheader trick) and
    class-based `background-image` (hero banners / button backgrounds).
    Only simple, comma-separated class selectors are handled (".a, .b
    {...}") - enough for the common case; anything more exotic (element
    selectors, descendant combinators, media queries) is harmlessly left
    alone rather than mishandled.
    """
    hidden_classes: set[str] = set()
    bg_classes: dict[str, str] = {}
    for block in _STYLE_BLOCK_RE.findall(html):
        for selectors, decls in _CLASS_RULE_RE.findall(block):
            # Only the first token in the capture group has already had its
            # leading "." consumed by the regex outside the group; later
            # comma-separated tokens (".a, .b") still carry theirs.
            names = [s.strip().lstrip(".") for s in selectors.split(",") if s.strip()]
            if not names or any(" " in n or "." in n[1:] for n in names):
                continue  # not a plain ".single-class" selector - skip it
            is_hidden = bool(_DISPLAY_NONE_RE.search(decls))
            bg_match = _BG_URL_RE.search(decls)
            for name in names:
                if is_hidden:
                    hidden_classes.add(name)
                if bg_match:
                    bg_classes[name] = bg_match.group(1)
    return hidden_classes, bg_classes


class _HtmlNormalizer(HTMLParser):
    """Rewrites raw email HTML into the subset QTextDocument actually
    renders correctly - see the module docstring for the three real,
    confirmed engine gaps this works around: image sizing,
    `display:none`, and `background-image`.

    Content this file doesn't have an opinion about passes through
    byte-for-byte via get_starttag_text()/original data, so this never
    risks corrupting the rest of a real newsletter's markup.
    """

    def __init__(self, max_width: int, hidden_classes: set[str],
                 bg_classes: dict[str, str]):
        super().__init__(convert_charrefs=False)
        self.max_width = max_width
        self._hidden_classes = hidden_classes
        self._bg_classes = bg_classes
        self.out: list[str] = []
        # src -> (declared_width, declared_height) for images that stated
        # both. Used to reserve correctly-shaped space before a remote
        # image arrives, so the page doesn't jump when it does.
        self.image_boxes: dict[str, tuple[int, int]] = {}
        # Tag names of ancestors currently being suppressed (display:none)
        # - non-empty means everything until it unwinds is dropped.
        self._skip_stack: list[str] = []

    # -- shared open-tag handling -----------------------------------------

    def handle_starttag(self, tag: str, attrs) -> None:
        self._handle_open(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self._handle_open(tag, attrs, self_closing=True)

    def _handle_open(self, tag: str, attrs, *, self_closing: bool) -> None:
        if self._skip_stack:
            if not self_closing:
                self._skip_stack.append(tag)
            return  # inside a hidden subtree: track nesting, emit nothing

        attrs_dict = {name.lower(): (value or "") for name, value in attrs}
        if self._is_hidden(attrs_dict):
            if not self_closing:
                self._skip_stack.append(tag)
            return

        if tag == "img":
            self._emit_img(attrs, self_closing=self_closing)
            return
        self._emit_generic(tag, attrs, attrs_dict, self_closing=self_closing)

    def _is_hidden(self, attrs_dict: dict[str, str]) -> bool:
        if _DISPLAY_NONE_RE.search(attrs_dict.get("style", "")):
            return True
        classes = attrs_dict.get("class", "").split()
        return any(c in self._hidden_classes for c in classes)

    def _bg_url_for(self, attrs_dict: dict[str, str]) -> str | None:
        match = _BG_URL_RE.search(attrs_dict.get("style", ""))
        if match:
            return match.group(1)
        for cls in attrs_dict.get("class", "").split():
            if cls in self._bg_classes:
                return self._bg_classes[cls]
        return None

    # -- <img> --------------------------------------------------------------

    def _emit_img(self, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> None:
        result: dict[str, str] = {}
        declared_width: int | None = None
        declared_height: int | None = None
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
                # Dropped from the emitted tag (see module docstring: a
                # mismatched width/height pair makes Qt slice the image),
                # but remembered so the pre-arrival placeholder can
                # reserve a correctly-shaped box.
                try:
                    declared_height = int(float(value.strip().rstrip("px")))
                except ValueError:
                    declared_height = None
                continue
            if key in _SIZE_ATTR_STRIP:
                continue  # srcset/sizes: responsive hints Qt can't use
            if key == "style":
                cleaned = _strip_size_styles(value)
                if cleaned:
                    result["style"] = cleaned
                continue
            result[name] = value

        if declared_width and declared_width > 0:
            result["width"] = str(min(declared_width, self.max_width))
            if declared_height and declared_height > 0:
                src = result.get("src") or result.get("SRC")
                if src:
                    self.image_boxes[src] = (declared_width, declared_height)
        # No declared width: left unset here: an oversized-but-undeclared
        # image is instead caught by the pixel-level cap in
        # HtmlMailView._on_image_fetched, since only the actual decoded
        # image data reveals whether it needs capping.

        pieces = [f'{k}="{v}"' for k, v in result.items()]
        tag_str = "<img " + " ".join(pieces) + (" />" if self_closing else ">")
        self.out.append(tag_str)

    # -- everything else: pass through, unless it carries a background-image

    def _emit_generic(self, tag: str, attrs: list[tuple[str, str | None]],
                      attrs_dict: dict[str, str], *, self_closing: bool) -> None:
        bg = self._bg_url_for(attrs_dict)
        if bg is None:
            self.out.append(self.get_starttag_text() or "")
            return

        if tag in _BACKGROUND_ATTR_TAGS and "background" not in attrs_dict:
            # Qt's rich-text engine natively honors this legacy attribute
            # on table/td/th/tr/body - the cleanest possible fix, no
            # visual approximation needed.
            piece_strs = [
                f'{name}="{value}"' if value is not None else f"{name}"
                for name, value in attrs
            ]
            piece_strs.append(f'background="{bg}"')
            self.out.append(
                "<" + tag + " " + " ".join(piece_strs) + (" />" if self_closing else ">")
            )
        else:
            # Qt has no way at all to show a CSS background-image on this
            # element - a synthetic <img> is the best available fallback
            # so the graphic is at least visible, even if not pixel-
            # perfect as a true background.
            self.out.append(self.get_starttag_text() or "")
            self.out.append(
                f'<img src="{bg}" style="display:block;max-width:100%;" alt="">'
            )

    # -- pass-through content, suppressed while inside a hidden subtree ---

    def handle_data(self, data: str) -> None:
        if not self._skip_stack:
            self.out.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self._skip_stack:
            self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip_stack:
            self.out.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        if not self._skip_stack:
            self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        if not self._skip_stack:
            self.out.append(f"<!{decl}>")

    def unknown_decl(self, data: str) -> None:
        if not self._skip_stack:
            self.out.append(f"<![{data}]>")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_stack:
            if self._skip_stack[-1] == tag:
                self._skip_stack.pop()
            elif tag in self._skip_stack:
                # Malformed nesting - pop up to and including this tag
                # rather than getting stuck suppressing forever.
                while self._skip_stack and self._skip_stack.pop() != tag:
                    pass
            return
        self.out.append(f"</{tag}>")

    def handle_pi(self, data: str) -> None:
        if not self._skip_stack:
            self.out.append(f"<?{data}>")


def normalize_email_html(html: str, max_width: int) -> tuple[str, dict[str, tuple[int, int]]]:
    """Rewrite raw email HTML into what QTextDocument actually renders
    correctly (see module docstring): image sizing, hidden-preheader
    removal, background-image conversion.

    Returns (html, image_boxes) where image_boxes maps an image src to
    the width/height it declared - the caller uses that to reserve a
    correctly-shaped placeholder so a remote image arriving later doesn't
    shove the whole layout around. Falls back to the original HTML
    unchanged if parsing hits something unexpected, rather than ever
    risking showing nothing.
    """
    if not html or not _NEEDS_NORMALIZATION.search(html):
        return html, {}
    try:
        hidden_classes, bg_classes = _extract_style_block_maps(html)
        parser = _HtmlNormalizer(max_width, hidden_classes, bg_classes)
        parser.feed(html)
        parser.close()
        return "".join(parser.out), parser.image_boxes
    except Exception as e:
        log.debug("HTML normalization skipped (%s)", e)
        return html, {}


def normalize_image_sizing(html: str, max_width: int) -> str:
    """The HTML half of normalize_email_html, for callers that don't need
    the reserved-space map."""
    return normalize_email_html(html, max_width)[0]


_PLACEHOLDER_SIZE = 28


@lru_cache(maxsize=256)
def _reserved_image_placeholder(width: int, height: int) -> QImage:
    """A placeholder with the SAME aspect ratio the <img> declared.

    This is what stops a promotional email from visibly reflowing while
    it loads. Qt sizes an image from the width in its char format and the
    resource's own aspect ratio, so handing back a correctly-shaped
    placeholder makes the document lay out at its final height on the
    very first paint - a 600x300 banner reserves a 600x300 box instead of
    a 28x28 square that later shoves everything below it down the page.
    """
    width = max(1, min(width, 2000))
    height = max(1, min(height, 2000))
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 18))
    radius = min(8, width / 4, height / 4)
    painter.drawRoundedRect(0, 0, width, height, radius, radius)
    painter.end()
    return image


@lru_cache(maxsize=1)
def _pending_image_placeholder() -> QImage:
    """A soft, neutral rounded box standing in for an image that hasn't
    arrived yet (or never will) - confirmed by direct rendering that Qt's
    own default for an unavailable ImageResource is a "broken document"
    glyph (a torn-corner page icon), which reads as an error rather than
    "still loading" and is exactly the "ugly/broken" first impression
    real promotional email had before this. Declared <img width="..">
    still scales this the same way it scales a real photo, so a wide
    banner gets a wide (if flatly gray) placeholder, not a tiny square.
    """
    size = _PLACEHOLDER_SIZE
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    # A faint black wash rather than a fixed color: reads as a quiet
    # placeholder against both the app's dark loading state and the
    # neutral light default new HTML content renders on.
    painter.setBrush(QColor(0, 0, 0, 20))
    painter.drawRoundedRect(0, 0, size, size, 6, 6)
    painter.end()
    return image


class _ImageBridge(QObject):
    """Delivers downloaded bytes from worker threads to the UI thread."""

    fetched = Signal(str, bytes)


class _NormalizeBridge(QObject):
    """Delivers a background thread-pool normalization result to the UI
    thread. A plain QRunnable can't emit signals itself (it isn't a
    QObject), so this is the same worker-to-UI handoff pattern
    _ImageBridge uses for fetched image bytes."""

    done = Signal(int, str, dict)  # generation, normalized HTML, image boxes


class _NormalizeTask(QRunnable):
    """Runs the CPU-bound HTML normalization pass (Python HTMLParser over
    the full message body) on a QThreadPool worker instead of the UI
    thread. For a real promotional email - deeply nested tables, several
    embedded images - this pass is real work; running it inline in
    set_email_html was measured to noticeably stall the UI thread on
    exactly the kind of email that triggered this rewrite."""

    def __init__(self, generation: int, html: str, max_width: int,
                 bridge: _NormalizeBridge):
        super().__init__()
        self.generation = generation
        self.html = html
        self.max_width = max_width
        self.bridge = bridge

    def run(self) -> None:
        normalized, boxes = normalize_email_html(self.html, self.max_width)
        self.bridge.done.emit(self.generation, normalized, boxes)


_MAX_CONCURRENT_IMAGE_FETCHES = 6


@lru_cache(maxsize=1)
def _image_fetch_pool() -> QThreadPool:
    """A dedicated pool for remote-image fetches, deliberately separate
    from QThreadPool.globalInstance() (used for HTML normalization).
    Sharing one pool between CPU-bound normalize work and I/O-bound
    network fetches would let an email with two dozen images (a real,
    common case) crowd out normalization for whatever's opened next, and
    would size fetch concurrency off the CPU core count - a number with
    nothing to do with how many sockets are reasonable to open on a real
    network at once. An explicit small cap keeps it predictable instead.
    """
    pool = QThreadPool()
    pool.setMaxThreadCount(_MAX_CONCURRENT_IMAGE_FETCHES)
    return pool


class _ImageFetchTask(QRunnable):
    """Downloads one remote image on a dedicated fetch-pool worker.
    Replaces a previous raw threading.Thread-per-image approach: an email
    with a couple dozen icons/tracking pixels used to spawn that many
    bare OS threads - and sockets - all at once."""

    def __init__(self, url: str, bridge: _ImageBridge):
        super().__init__()
        self.url = url
        self.bridge = bridge

    def run(self) -> None:
        try:
            req = urllib.request.Request(
                self.url, headers={"User-Agent": "Unified/1.0"}
            )
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
                data = resp.read(_MAX_IMAGE_BYTES + 1)
            if len(data) > _MAX_IMAGE_BYTES:
                log.info("Image too large, skipped: %s", self.url)
                return
            self.bridge.fetched.emit(self.url, data)
        except Exception as e:
            log.debug("Image fetch failed (%s): %s", self.url, e)


# Schemes an email is allowed to send to the OS handler. Everything else -
# file:, smb:, javascript:, ms-msdt:, search-ms:, and every other
# shell-registered protocol - is refused, because openUrl() on Windows is
# ShellExecute and will happily launch a local executable or reach out to
# an attacker's SMB share.
_SAFE_LINK_SCHEMES = frozenset({"http", "https", "mailto"})


class HtmlMailView(QTextBrowser):
    # Emitted with the number of distinct remote images withheld, so the
    # reading pane can offer a "load images" affordance for this message.
    remote_images_blocked = Signal(int)
    # Emitted with the raw URL when a link is refused for having an unsafe
    # scheme, so the UI can tell the user rather than silently no-op.
    unsafe_link_blocked = Signal(str)
    # The app's dark chrome and an email's own visual design are two
    # separate things (see module docstring). This widget's app-wide QSS
    # rule (#emailBody) supplies the card border/radius/padding either
    # way; only background/text color toggle here, between:
    #  - the app's own dark palette, while showing a loading/status
    #    message or a plain-text body (there's no "email theme" to
    #    preserve for those - they're either app UI or unstyled text)
    #  - a neutral light default, once real HTML content is on screen -
    #    matching what every real email client falls back to for mail
    #    that doesn't declare its own background/color. An email that
    #    *does* declare its own (light or dark) already renders with
    #    those colors regardless of this default - confirmed empirically:
    #    QTextDocument's own background-color CSS takes precedence over
    #    the widget's stylesheet background wherever the HTML sets one.
    _CONTENT_THEME_QSS = "QTextBrowser#emailBody { background: #ffffff; color: #1a1a1a; }"

    def __init__(self, parent=None):
        super().__init__(parent)
        # NOT setOpenExternalLinks(True): that hands every anchor in a
        # hostile email straight to QDesktopServices.openUrl(), which on
        # Windows is ShellExecute. A link to file:///C:/.../payload.exe
        # would launch it, and a file://attacker/share UNC path would leak
        # the user's NTLM hash to an SMB server. Anchors are handled by
        # _on_anchor_clicked instead, behind a scheme allowlist.
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor_clicked)
        # Only takes effect for plain-text bodies - real HTML mail carries
        # its own fonts, which this deliberately never overrides.
        self.setFont(t.make_font("body"))
        self._html = ""
        self._images: dict[str, QImage] = {}
        self._pending: set[str] = set()
        # Remote images are blocked until the user asks for them, per
        # message - the same default Thunderbird and Outlook use. Loading
        # them automatically turns every tracking pixel into a read
        # receipt, and lets an email probe hosts only this machine can
        # reach (http://192.168.x.x/, http://169.254.169.254/, ...).
        self._allow_remote_images = False
        self._blocked_remote: set[str] = set()
        # src -> declared (width, height), from normalization; drives the
        # correctly-shaped placeholder that keeps layout stable.
        self._image_boxes: dict[str, tuple[int, int]] = {}
        self._bridge = _ImageBridge()
        self._bridge.fetched.connect(self._on_image_fetched)
        self._normalize_bridge = _NormalizeBridge()
        self._normalize_bridge.done.connect(self._on_normalized)
        # Bumped on every set_email_html/set_email_text call; a normalize
        # result whose generation doesn't match the current one is from an
        # email the user already navigated away from and is discarded -
        # otherwise a slow background result for a previous message could
        # land after a faster one for the message actually on screen.
        self._generation = 0
        # Coalesce re-renders when many images arrive close together.
        self._rerender_timer = QTimer(self)
        self._rerender_timer.setSingleShot(True)
        self._rerender_timer.setInterval(150)
        self._rerender_timer.timeout.connect(self._rerender)

    # ------------------------------------------------------------------ public

    def set_email_html(self, html: str) -> None:
        self._images.clear()  # previous message's decoded images are done
        self._pending.clear()
        self._image_boxes = {}
        self._html = ""
        self._generation += 1
        # Image consent is per message: opting one newsletter in must not
        # silently opt in the next sender too.
        self._allow_remote_images = False
        self._blocked_remote.clear()
        # "Rendering message..." is an app status line, not email content -
        # stays on the app's own dark palette until real HTML lands.
        self.setStyleSheet("")
        # Immediate, lightweight feedback: normalizing a real promotional
        # email's HTML is real CPU work (nested tables, several images) -
        # the pane must never sit looking frozen while that happens off
        # the UI thread.
        self.setPlainText("Rendering message...")
        task = _NormalizeTask(
            self._generation, html, self._max_width(), self._normalize_bridge
        )
        QThreadPool.globalInstance().start(task)

    def set_email_text(self, text: str) -> None:
        self._images.clear()
        self._html = ""
        self._pending.clear()
        self._generation += 1  # invalidate any normalize task still in flight
        self.setStyleSheet("")  # plain text has no theme of its own to preserve
        self.setPlainText(text)

    def _on_normalized(self, generation: int, normalized_html: str,
                       image_boxes: dict) -> None:
        if generation != self._generation:
            return  # stale - the user has since moved to a different email
        self._html = normalized_html
        self._image_boxes = image_boxes or {}
        # Switch to the neutral light default just before real content
        # lands - an email that sets its own background/color still wins
        # over this, only an email that sets neither falls back to it.
        self.setStyleSheet(self._CONTENT_THEME_QSS)
        self.setHtml(self._html)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """Open a clicked link only if its scheme is one an email is
        allowed to hand to the OS. See _SAFE_LINK_SCHEMES."""
        scheme = (url.scheme() or "").lower()
        if scheme in _SAFE_LINK_SCHEMES:
            QDesktopServices.openUrl(url)
            return
        log.warning("Refused to open a link with unsafe scheme %r from an email",
                    scheme or "(none)")
        self.unsafe_link_blocked.emit(url.toString())

    def set_remote_images_allowed(self, allowed: bool) -> None:
        """Opt this message in to loading remote images. Re-renders so
        loadResource runs again and the fetches actually start."""
        if allowed == self._allow_remote_images:
            return
        self._allow_remote_images = allowed
        if allowed and self._html:
            self._blocked_remote.clear()
            self.setHtml(self._html)

    def has_blocked_remote_images(self) -> bool:
        return bool(self._blocked_remote)

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
                return _pending_image_placeholder()
            if url.scheme() in ("http", "https"):
                if not self._allow_remote_images:
                    # Blocked: no request is made at all, so nothing is
                    # disclosed to the sender. The reserved placeholder
                    # below still holds the right space, so choosing to
                    # load images later doesn't reflow the page.
                    if key not in self._blocked_remote:
                        self._blocked_remote.add(key)
                        self.remote_images_blocked.emit(len(self._blocked_remote))
                elif key not in self._pending:
                    self._pending.add(key)
                    _image_fetch_pool().start(_ImageFetchTask(key, self._bridge))
            # Not fetched yet: a soft neutral placeholder rather than
            # Qt's own default resource glyph, which is a torn-page
            # "broken image" icon - it reads as an error, not as "still
            # loading", which is what a remote image not being back yet
            # actually means most of the time. When the tag declared its
            # dimensions, the placeholder takes that exact shape so the
            # document lays out at its final height immediately and does
            # not reflow when the real image lands.
            box = self._image_boxes.get(key)
            if box:
                return _reserved_image_placeholder(box[0], box[1])
            return _pending_image_placeholder()
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
        """Lay out newly arrived images without re-parsing the HTML from
        scratch. A full setHtml() re-run was the previous approach here;
        for a message with several images trickling in at different
        network speeds, that meant a full HTML re-parse per image,
        repeatedly blocking the UI thread for a document that was already
        parsed once. markContentsDirty forces Qt to re-run layout (which
        re-resolves each image reference against the resource cache
        addResource already updated) without repeating the parse."""
        bar = self.verticalScrollBar()
        pos = bar.value()
        self.document().markContentsDirty(0, self.document().characterCount())
        bar.setValue(pos)

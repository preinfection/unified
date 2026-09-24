"""Settings > Changelog: the published releases, newest first, as a page
of this app rather than a piece of GitHub.

ADAPTED FROM MAGIC UI'S CHANGELOG TEMPLATE. What that layout gets right is
a two-column rhythm: the version and date in a narrow left column, the
notes in a wide right one, each release closed by a hairline - so a
reader can run down the left edge to find a version and read across to
see what changed. That is kept. The template's web furniture is not: no
cards, no images, no avatars, no asset lists, no embedded page. The type,
spacing, hairlines and selection are the same ones every other Settings
page uses.

RELEASE NOTES ARE UNTRUSTED TEXT. Whatever GitHub returns is rendered by
a deliberately small Markdown subset - headings, bullet and numbered
lists, bold, italic, inline code, paragraphs - built from escaped text.
Images are dropped, raw HTML is dropped, and links become their text. A
release body cannot load a remote image (a tracking pixel), run anything,
or send the reader anywhere.
"""

from __future__ import annotations

import html
import re
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.services.updates import Release, ReleaseNotesStore, is_newer, parse_version
from app.ui import theme as t
from app.ui.components.primitives import Rule
from app.ui.components.section_header import SectionHeader

# Lines that start with a bullet glyph instead of "-" or "*" - real release
# notes in this repository use "◉" - are still list items.
_BULLET = re.compile(r"^\s*(?:[-*+]|[•◉●○▪■◦–])\s+(.*)$")
_NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_AUTOLINK = re.compile(r"<(https?://[^>]+)>")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def _inline(text: str) -> str:
    """Escape, then allow **bold**, *italic*/_italic_ and `code`."""
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _AUTOLINK.sub(r"\1", text)
    text = _HTML_TAG.sub("", text)
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if len(part) > 1 and part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue
        chunk = html.escape(part)
        chunk = re.sub(r"\*\*(.+?)\*\*|__(.+?)__",
                       lambda m: f"<b>{m.group(1) or m.group(2)}</b>", chunk)
        chunk = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", chunk)
        chunk = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<i>\1</i>", chunk)
        out.append(chunk)
    return "".join(out)


def _restates_version(heading: str, release: Release | None) -> bool:
    """A leading "## v1.3.0" or "# Unified v1.2.1" repeats what the left
    column already says."""
    if release is None:
        return False
    words = re.findall(r"[vV]?\d+(?:\.\d+)+", heading)
    return any(parse_version(w) == parse_version(release.tag) for w in words)


def render_markdown(md: str, release: Release | None = None) -> str:
    """Release-note Markdown -> the small HTML subset QLabel renders.

    Paragraph lines are joined (the notes here are hard-wrapped at 72
    columns, and keeping those breaks would give a ragged edge in a wider
    column); list items, headings and rules are their own blocks.
    """
    lines = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []
    list_tag = ""
    in_code = False
    code: list[str] = []
    first_block = True

    def close_paragraph() -> None:
        nonlocal first_block
        if paragraph:
            blocks.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()
            first_block = False

    def close_list() -> None:
        nonlocal list_tag, first_block
        if items:
            body = "".join(f"<li>{item}</li>" for item in items)
            blocks.append(f"<{list_tag}>{body}</{list_tag}>")
            items.clear()
            first_block = False
        list_tag = ""

    for raw in lines:
        if raw.strip().startswith("```"):
            if in_code:
                blocks.append("<pre>" + html.escape("\n".join(code)) + "</pre>")
                code.clear()
                in_code = False
            else:
                close_paragraph()
                close_list()
                in_code = True
            continue
        if in_code:
            code.append(raw)
            continue

        line = raw.rstrip()
        if not line.strip():
            close_paragraph()
            close_list()
            continue
        heading = _HEADING.match(line)
        if heading:
            close_paragraph()
            close_list()
            text = heading.group(2)
            if first_block and _restates_version(text, release):
                first_block = False
                continue
            level = min(3, len(heading.group(1)) + 1)
            blocks.append(f"<h{level}>{_inline(text)}</h{level}>")
            first_block = False
            continue
        if _RULE.match(line):
            close_paragraph()
            close_list()
            continue
        bullet = _BULLET.match(line)
        numbered = _NUMBERED.match(line)
        if bullet or numbered:
            close_paragraph()
            tag = "ul" if bullet else "ol"
            if list_tag and list_tag != tag:
                close_list()
            list_tag = tag
            items.append(_inline((bullet or numbered).group(1 if bullet else 2)))
            continue
        if items and raw.startswith(("  ", "\t")):
            # A wrapped continuation of the previous list item.
            items[-1] += " " + _inline(line.strip())
            continue
        close_list()
        paragraph.append(line.strip())

    if in_code and code:
        blocks.append("<pre>" + html.escape("\n".join(code)) + "</pre>")
    close_paragraph()
    close_list()
    return "".join(blocks)


def release_title(release: Release) -> str:
    """The release's name minus the version it restates:
    "Unified v1.3.0 - full UI/UX redesign" -> "Full UI/UX redesign", and
    "v1.2.1" -> "" (the left column already says it)."""
    rest = re.sub(r"^\s*(Unified\s+)?[vV]?\d+(\.\d+)+\s*[-–—:]?\s*", "",
                  release.name or "").strip()
    return rest[:1].upper() + rest[1:]


def _date(published_at: str) -> str:
    try:
        stamp = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return f"{stamp.day} {stamp.strftime('%b %Y')}"


def _styled(html_text: str) -> str:
    """Give each element the app's type and ink INLINE.

    QLabel's rich-text engine keeps its own built-in heading sizes and
    ignores a <style> block's font-size for them, which made a heading
    inside the notes as large as the release title above it. Inline style
    attributes are honoured, so the tokens land exactly.
    """
    styles = {
        "p": f"margin: 0 0 {t.SPACE_SM}px 0;",
        "h2": (f"font-size: {t.SIZE_LG}px; font-weight: {t.WEIGHT_SEMIBOLD};"
               f" margin: {t.SPACE_MD}px 0 {t.SPACE_XS}px 0; color: {t.TEXT_PRIMARY};"),
        "h3": (f"font-size: {t.SIZE_MD}px; font-weight: {t.WEIGHT_SEMIBOLD};"
               f" margin: {t.SPACE_SM}px 0 {t.SPACE_XS}px 0; color: {t.TEXT_PRIMARY};"),
        "h4": (f"font-size: {t.SIZE_MD}px; font-weight: {t.WEIGHT_SEMIBOLD};"
               f" margin: {t.SPACE_SM}px 0 {t.SPACE_XS}px 0; color: {t.TEXT_PRIMARY};"),
        "ul": f"margin: 0 0 {t.SPACE_SM}px 0; -qt-list-indent: 1;",
        "ol": f"margin: 0 0 {t.SPACE_SM}px 0; -qt-list-indent: 1;",
        "li": "margin: 0 0 2px 0;",
        "code": f"font-family: {t.FONT_MONO_CSS}; font-size: {t.SIZE_SM}px;",
        "pre": f"font-family: {t.FONT_MONO_CSS}; font-size: {t.SIZE_SM}px;",
    }
    for tag, style in styles.items():
        html_text = html_text.replace(f"<{tag}>", f'<{tag} style="{style}">')
    return html_text


class _Entry(QWidget):
    """One release: version and date on the left, the notes on the right."""

    LEFT = 112

    def __init__(self, release: Release, current: str, parent=None):
        super().__init__(parent)
        self.release = release
        row = QHBoxLayout(self)
        row.setContentsMargins(0, t.SPACE_LG, 0, t.SPACE_LG)
        row.setSpacing(t.SPACE_XL)

        left = QVBoxLayout()
        left.setSpacing(t.SPACE_XXS)
        version = QLabel(f"v{release.version}")
        version.setFont(_version_font())
        t.role(version, "primary")
        left.addWidget(version)
        date = QLabel(_date(release.published_at))
        date.setFont(t.make_font("caption"))
        t.role(date, "tertiary")
        left.addWidget(date)
        note = ""
        if is_newer(release.tag, current):
            note = "Newer than this copy"
        elif parse_version(release.tag) == parse_version(current):
            note = "This copy"
        self.marker = QLabel(note)
        self.marker.setFont(t.make_font("caption"))
        t.role(self.marker, "secondary")
        self.marker.setVisible(bool(note))
        left.addWidget(self.marker)
        left.addStretch(1)
        holder = QWidget()
        holder.setLayout(left)
        holder.setFixedWidth(self.LEFT)
        row.addWidget(holder, 0, Qt.AlignmentFlag.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(t.SPACE_XS)
        title_text = release_title(release)
        if title_text:
            title = QLabel(title_text)
            title.setFont(t.make_font("section_heading"))
            title.setWordWrap(True)
            t.role(title, "primary")
            right.addWidget(title)
        body_html = render_markdown(release.body, release)
        self.body = QLabel(_styled(body_html or "<p>No notes were published "
                                             "with this release.</p>"))
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setWordWrap(True)
        self.body.setOpenExternalLinks(False)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setFont(t.make_font("field_value"))
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        t.role(self.body, "secondary")
        right.addWidget(self.body)
        row.addLayout(right, stretch=1)


def _version_font():
    font = t.make_font("badge")
    font.setPixelSize(t.SIZE_MD)
    return font


class ChangelogPage(QWidget):
    """Header, a status line, and the entries in a scroll area.

    The network is asked only when the page is first shown - someone who
    never opens it never causes a request - and at most once an hour.
    """

    def __init__(self, store: ReleaseNotesStore, current: str = __version__,
                 parent=None):
        super().__init__(parent)
        self._store = store
        self._current = current
        self._requested = False

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(t.SPACE_SM)
        col.addWidget(SectionHeader("Changelog"))

        self.status = QLabel("")
        self.status.setFont(t.make_font("caption"))
        self.status.setWordWrap(True)
        t.role(self.status, "tertiary")
        col.addWidget(self.status)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list = QWidget()
        self._list.setObjectName("changelogList")
        self._rows = QVBoxLayout(self._list)
        self._rows.setContentsMargins(0, 0, t.SPACE_SM, 0)
        self._rows.setSpacing(0)
        self._rows.addStretch(1)
        self._scroll.setWidget(self._list)
        col.addWidget(self._scroll, stretch=1)

        self.entries: list[_Entry] = []
        store.changed.connect(self._show)
        if store.releases:
            self._show(list(store.releases), "cached")
        else:
            self._set_status("loading")

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._requested:
            self._requested = True
            self._store.refresh()

    def _set_status(self, status: str) -> None:
        copy = f"This copy of Unified is v{self._current}."
        text = {
            "loading": "Loading release notes from GitHub…",
            "failed": "Release notes could not be loaded. Unified will try "
                      "again the next time this page is opened.",
            "empty": "No releases have been published yet.",
            "stale": "Could not reach GitHub, so these are the notes saved "
                     "the last time it could. " + copy,
            "cached": "Published releases, newest first. " + copy,
            "fresh": "Published releases, newest first. " + copy,
        }.get(status, "")
        self.status.setText(text)

    def _show(self, releases: list, status: str) -> None:
        self._set_status(status)
        shown = [e.release for e in self.entries]
        if shown == releases:
            return
        for entry in self.entries:
            entry.setParent(None)
            entry.deleteLater()
        self.entries = []
        # Remove the old hairlines as well (everything but the stretch).
        while self._rows.count() > 1:
            item = self._rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for index, release in enumerate(releases):
            entry = _Entry(release, self._current)
            if index:
                self._rows.insertWidget(self._rows.count() - 1, Rule())
            self._rows.insertWidget(self._rows.count() - 1, entry)
            self.entries.append(entry)

    def retheme(self) -> None:
        # The notes carry their own <style> with token values in it, so a
        # new palette means building the entries again.
        releases = [e.release for e in self.entries]
        self._show([], self._store.status)
        self._show(releases, self._store.status)

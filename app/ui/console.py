"""The console: Unified's own log, as a quiet terminal-style surface.

A logging.Handler forwards every INFO+ record through a Qt signal, so
messages logged from worker threads land safely on the UI thread. Records
are kept with a category (SYNC / DATABASE / API / APP) derived from the
logger name so the pane can be filtered. Secrets never appear because the
app never logs tokens or passwords.

=========================================================================
ADAPTED FROM MAGIC UI'S TERMINAL, AND WHAT WAS LEFT BEHIND

That component is a card with a title strip, a hairline under it, and
monospace lines with real space between them - and it reads as a
terminal because of the TYPE and the RHYTHM, not the chrome. That is what
is kept: a title strip carrying the controls, one hairline, a mono face
at a comfortable leading, and columns that line up (time, level, source,
message) so a long log can be scanned down one edge.

Left behind on purpose:

  * THE TRAFFIC LIGHTS. Three coloured dots are another operating system's
    window controls drawn as decoration. On Windows they mean nothing, and
    PRODUCT.md forbids exactly this kind of ornament.
  * LINES TYPING THEMSELVES OUT. This is a live log; a line that is still
    animating when the next one arrives is a line nobody can read, and a
    burst of sync activity would queue seconds of choreography. New lines
    simply appear, batched, so a burst of five hundred costs one repaint.
  * A BLINKING CURSOR. Nothing in this app pulses. The prompt at the tail
    is steady, and it is there only while the log is FOLLOWING new output:
    scroll up to read and it goes, along with the Follow switch, so the
    pane itself says whether it is live.

COLOUR IS A SIGNAL HERE TOO. Timestamps, sources and INFO are the quiet
ink; a WARN tag is the warning hue and an ERROR tag the error hue, and
nothing else in the pane has colour - so a scroll through a thousand lines
stops exactly where something went wrong.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme as t
from app.ui.components.primitives import Button, Variant
from app.ui.components.toggle import Toggle
from app.ui.svg_icon import simple_icon

MAX_RECORDS = 3000

CAT_SYNC = "SYNC"
CAT_DB = "DATABASE"
CAT_API = "API"
CAT_OTHER = "APP"

FILTERS = ["ALL", CAT_SYNC, "ERRORS", CAT_DB, CAT_API]
_FILTER_LABELS = {"ALL": "All", CAT_SYNC: "Sync", "ERRORS": "Problems",
                  CAT_DB: "Database", CAT_API: "Network"}
# The source column is four characters wide in every row, so the messages
# start on one vertical line.
_SOURCE_TAG = {CAT_SYNC: "SYNC", CAT_DB: "DB", CAT_API: "API", CAT_OTHER: "APP"}

# How long records wait before being drawn. A sync burst logs hundreds of
# lines in a second; drawing each one as it arrives would repaint the pane
# hundreds of times. At 80ms the log still reads as live.
FLUSH_MS = 80
FONT_PX = 12
LINE_HEIGHT = 150      # percent of the face's own line spacing


def categorize(logger_name: str) -> str:
    if "sync_service" in logger_name or "account_manager" in logger_name:
        return CAT_SYNC
    if "database" in logger_name:
        return CAT_DB
    if any(part in logger_name for part in
           ("gmail", "imap", "smtp", "oauth", "googleapiclient", "auth", "updates")):
        return CAT_API
    return CAT_OTHER


def level_tag(levelno: int) -> str:
    if levelno >= logging.ERROR:
        return "ERROR"
    if levelno >= logging.WARNING:
        return "WARN"
    return "INFO"


class _LogBridge(QObject):
    # category, levelno, "HH:MM:SS", message (with traceback, if any)
    record = Signal(str, int, str, str)


class QtLogHandler(logging.Handler):
    def __init__(self, bridge: _LogBridge):
        super().__init__(level=logging.INFO)
        self.bridge = bridge
        # Message only: the time and the level are columns of their own.
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
            self.bridge.record.emit(
                categorize(record.name), record.levelno, stamp, self.format(record)
            )
        except RuntimeError:
            pass  # bridge destroyed during shutdown


def _mono(px: int = FONT_PX) -> QFont:
    font = QFont()
    font.setFamilies(t.FONT_MONO)
    font.setPixelSize(px)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class _LogView(QTextEdit):
    """The log body: selectable text, plus two things painted over it -
    the steady prompt at the tail while following, and the empty state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("console")
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setFont(_mono())
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.document().setMaximumBlockCount(MAX_RECORDS)
        self.document().setDocumentMargin(t.SPACE_MD)
        root = self.document().rootFrame().frameFormat()
        # Room under the last line for the prompt, so it never overlaps
        # the newest record.
        root.setBottomMargin(self._line_height() + t.SPACE_XS)
        self.document().rootFrame().setFrameFormat(root)
        self.following = True
        self.empty_title = ""
        self.empty_detail = ""

    def _line_height(self) -> float:
        return QFontMetricsF(self.font()).lineSpacing() * LINE_HEIGHT / 100.0

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.document().isEmpty():
            self._paint_empty(painter)
        elif self.following:
            self._paint_prompt(painter)
        painter.end()

    def _paint_prompt(self, painter: QPainter) -> None:
        layout = self.document().documentLayout()
        last = self.document().lastBlock()
        rect = layout.blockBoundingRect(last)
        y = rect.bottom() - self.verticalScrollBar().value()
        line = self._line_height()
        if y > self.viewport().height():
            return
        metrics = QFontMetricsF(self.font())
        x = self.document().documentMargin()
        baseline = y + (line + metrics.ascent() - metrics.descent()) / 2.0
        painter.setFont(self.font())
        painter.setPen(QColor(t.TEXT_TERTIARY))
        prompt = "\u203a"
        painter.drawText(QPointF(x, baseline), prompt)
        caret = QRectF(x + metrics.horizontalAdvance(prompt + " "),
                       y + (line - metrics.height()) / 2.0,
                       max(2.0, metrics.horizontalAdvance("M") * 0.55),
                       metrics.height())
        colour = QColor(t.ACCENT)
        colour.setAlphaF(0.55)
        painter.fillRect(caret, colour)

    def _paint_empty(self, painter: QPainter) -> None:
        area = QRectF(self.viewport().rect())
        title = QFont(t.make_font("status"))
        detail = QFont(t.make_font("caption"))
        th = QFontMetricsF(title).height()
        dh = QFontMetricsF(detail).height()
        top = area.center().y() - (th + t.SPACE_XS + dh) / 2.0
        painter.setFont(title)
        painter.setPen(QColor(t.TEXT_SECONDARY))
        painter.drawText(QRectF(area.left(), top, area.width(), th),
                         Qt.AlignmentFlag.AlignCenter, self.empty_title)
        painter.setFont(detail)
        painter.setPen(QColor(t.TEXT_TERTIARY))
        painter.drawText(QRectF(area.left(), top + th + t.SPACE_XS, area.width(), dh),
                         Qt.AlignmentFlag.AlignCenter, self.empty_detail)


class ConsoleWidget(QWidget):
    """Title strip with filters and Follow/Copy/Clear, over the log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("consolePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # (category, levelno, stamp, message) ring buffer; the source of
        # truth for re-filtering and re-theming.
        self._records: deque[tuple[str, int, str, str]] = deque(maxlen=MAX_RECORDS)
        self._pending: list[tuple[str, int, str, str]] = []
        self._filter = "ALL"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_strip())

        self.view = _LogView()
        layout.addWidget(self.view, stretch=1)
        self.view.verticalScrollBar().valueChanged.connect(self._on_scrolled)
        self.view.verticalScrollBar().rangeChanged.connect(self._on_range_changed)

        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(FLUSH_MS)
        self._flush_timer.timeout.connect(self._flush)

        self._build_formats()
        self._update_empty_text()

        self._bridge = _LogBridge()
        self._bridge.record.connect(self._on_record)
        self._handler = QtLogHandler(self._bridge)
        logging.getLogger().addHandler(self._handler)

    # ------------------------------------------------------------- building

    def _build_strip(self) -> QWidget:
        strip = QWidget()
        strip.setObjectName("consoleStrip")
        strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        strip.setFixedHeight(t.HEIGHT_MD + t.SPACE_SM)
        row = QHBoxLayout(strip)
        row.setContentsMargins(t.SPACE_MD, 0, t.SPACE_SM, 0)
        row.setSpacing(t.SPACE_XS)

        self._glyph = QLabel()
        self._glyph.setPixmap(simple_icon("console", 14, t.TEXT_TERTIARY).pixmap(14, 14))
        row.addWidget(self._glyph)
        row.addSpacing(t.SPACE_XS)
        title = QLabel("Console")
        title.setFont(t.make_font("status"))
        t.role(title, "secondary")
        row.addWidget(title)
        row.addSpacing(t.SPACE_LG)

        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_buttons: dict[str, QPushButton] = {}
        for name in FILTERS:
            btn = QPushButton(_FILTER_LABELS[name])
            btn.setObjectName("consoleFilter")
            btn.setCheckable(True)
            btn.setChecked(name == "ALL")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(t.make_font("caption"))
            btn.clicked.connect(lambda _=False, n=name: self._set_filter(n))
            self._filter_group.addButton(btn)
            self._filter_buttons[name] = btn
            row.addWidget(btn)
        row.addStretch(1)

        follow_label = QLabel("Follow")
        follow_label.setFont(t.make_font("caption"))
        t.role(follow_label, "tertiary")
        self.follow_toggle = Toggle()
        self.follow_toggle.setChecked(True)
        self.follow_toggle.setAccessibleName("Follow new lines")
        self.follow_toggle.setToolTip("Keep the newest line in view")
        self.follow_toggle.toggled.connect(self._on_follow_toggled)
        follow_label.setBuddy(self.follow_toggle)
        row.addWidget(follow_label)
        row.addWidget(self.follow_toggle)
        row.addSpacing(t.SPACE_SM)

        self.copy_btn = Button("Copy", Variant.GHOST)
        self.copy_btn.setObjectName("consoleAction")
        self.copy_btn.setToolTip("Copy the lines shown")
        self.copy_btn.clicked.connect(self._copy)
        row.addWidget(self.copy_btn)
        self.clear_btn = Button("Clear", Variant.GHOST)
        self.clear_btn.setObjectName("consoleAction")
        self.clear_btn.setToolTip("Clear the console (the log file is kept)")
        self.clear_btn.clicked.connect(self._clear)
        row.addWidget(self.clear_btn)
        for btn in (self.copy_btn, self.clear_btn):
            btn.setMinimumHeight(t.HEIGHT_SM)
            btn.setFixedHeight(t.HEIGHT_SM)
        return strip

    def _build_formats(self) -> None:
        def fmt(colour: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(colour))
            f.setFont(_mono(), QTextCharFormat.FontPropertiesInheritanceBehavior.FontPropertiesAll)
            if bold:
                f.setFontWeight(t.WEIGHT_SEMIBOLD)
            return f

        self._fmt_quiet = fmt(t.TEXT_TERTIARY)
        self._fmt_text = fmt(t.TEXT_SECONDARY)
        self._fmt_level = {
            "INFO": fmt(t.TEXT_TERTIARY),
            "WARN": fmt(t.WARNING, bold=True),
            "ERROR": fmt(t.ERROR, bold=True),
        }
        # Problems read in the primary ink as well as carrying a hue, so
        # the message - not only the tag - stands out when scanning.
        self._fmt_problem = fmt(t.TEXT_PRIMARY)
        self._block = QTextBlockFormat()
        self._block.setLineHeight(
            float(LINE_HEIGHT),
            int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value),
        )
        # A HANGING INDENT: a long message wraps under its own first word,
        # not back under the timestamp, so the time/level/source columns
        # stay clear all the way down and the eye can run down them.
        indent = QFontMetricsF(_mono()).horizontalAdvance("00:00:00  ERROR  SYNC  ")
        self._block.setLeftMargin(indent)
        self._block.setTextIndent(-indent)

    # ------------------------------------------------------------ filtering

    def _matches(self, category: str, level: int) -> bool:
        if self._filter == "ALL":
            return True
        if self._filter == "ERRORS":
            return level >= logging.WARNING
        return category == self._filter

    def _set_filter(self, name: str) -> None:
        self._filter = name
        self._filter_buttons[name].setChecked(True)
        self._update_empty_text()
        self._rebuild()

    def _update_empty_text(self) -> None:
        if self._filter == "ALL":
            self.view.empty_title = "No activity yet"
            self.view.empty_detail = ("Syncs, warnings and errors appear here "
                                      "as they happen.")
        elif self._filter == "ERRORS":
            self.view.empty_title = "No problems"
            self.view.empty_detail = "Nothing has gone wrong this session."
        else:
            label = _FILTER_LABELS[self._filter].lower()
            self.view.empty_title = f"No {label} activity yet"
            self.view.empty_detail = "Choose All to see everything."
        self.view.viewport().update()

    # --------------------------------------------------------------- records

    def _on_record(self, category: str, level: int, stamp: str, message: str) -> None:
        record = (category, level, stamp, message)
        self._records.append(record)
        if self._matches(category, level):
            self._pending.append(record)
            if not self._flush_timer.isActive():
                self._flush_timer.start()

    def _append(self, cursor: QTextCursor, record) -> None:
        category, level, stamp, message = record
        tag = level_tag(level)
        if not self.view.document().isEmpty():
            cursor.insertBlock(self._block)
        else:
            cursor.setBlockFormat(self._block)
        cursor.insertText(f"{stamp}  ", self._fmt_quiet)
        cursor.insertText(f"{tag:<5}  ", self._fmt_level[tag])
        cursor.insertText(f"{_SOURCE_TAG.get(category, 'APP'):<4}  ", self._fmt_quiet)
        cursor.insertText(message, self._fmt_problem if tag != "INFO" else self._fmt_text)

    def _flush(self) -> None:
        """Draw every pending record in one edit - one layout, one repaint,
        however many arrived."""
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        bar = self.view.verticalScrollBar()
        keep = bar.value()
        cursor = QTextCursor(self.view.document())
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for record in batch:
            self._append(cursor, record)
        cursor.endEditBlock()
        if self.view.following:
            self._scroll_to_bottom()
        else:
            bar.setValue(keep)

    def _rebuild(self) -> None:
        """Re-render everything that passes the filter (a filter change or
        a theme change). One edit block, so it is one layout."""
        self._pending = []
        self.view.clear()
        cursor = QTextCursor(self.view.document())
        cursor.beginEditBlock()
        for record in self._records:
            if self._matches(record[0], record[1]):
                self._append(cursor, record)
        cursor.endEditBlock()
        self._set_following(True)
        self._scroll_to_bottom()
        self.view.viewport().update()

    # --------------------------------------------------------------- follow

    def _scroll_to_bottom(self) -> None:
        bar = self.view.verticalScrollBar()
        self._programmatic_scroll = True
        bar.setValue(bar.maximum())
        self._programmatic_scroll = False

    _programmatic_scroll = False

    def _on_scrolled(self, value: int) -> None:
        """Reading back through the log pauses following; returning to the
        end resumes it - the way every terminal behaves."""
        if self._programmatic_scroll:
            return
        at_end = value >= self.view.verticalScrollBar().maximum() - 2
        self._set_following(at_end)

    def _on_range_changed(self, _min: int, _max: int) -> None:
        if self.view.following:
            self._scroll_to_bottom()

    def _set_following(self, following: bool) -> None:
        if self.view.following == following:
            return
        self.view.following = following
        self.follow_toggle.blockSignals(True)
        self.follow_toggle.setChecked(following)
        self.follow_toggle._set_knob_pos(1.0 if following else 0.0)
        self.follow_toggle.blockSignals(False)
        self.view.viewport().update()

    def _on_follow_toggled(self, on: bool) -> None:
        self.view.following = on
        if on:
            self._scroll_to_bottom()
        self.view.viewport().update()

    def is_following(self) -> bool:
        return self.view.following

    # ---------------------------------------------------------------- actions

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.view.toPlainText())

    def _clear(self) -> None:
        self._records.clear()
        self._pending = []
        self.view.clear()
        self._set_following(True)
        self.view.viewport().update()

    def retheme(self) -> None:
        """Every line carries its colour in its own format, so a new palette
        means re-rendering the records - once, in one edit."""
        self._glyph.setPixmap(simple_icon("console", 14, t.TEXT_TERTIARY).pixmap(14, 14))
        self._build_formats()
        self._rebuild()

    # convenience for the main window and tests
    def toPlainText(self) -> str:  # noqa: N802 (Qt naming kept for callers)
        self._flush()
        return self.view.toPlainText()

    def detach(self) -> None:
        logging.getLogger().removeHandler(self._handler)

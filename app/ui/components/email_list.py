"""Virtualized email list: QAbstractListModel + QStyledItemDelegate +
QListView, instead of one QTreeWidgetItem per row.

This is the one part of the redesign with real performance stakes -
mailboxes here run to 10,000+ cached messages. A delegate paints each
visible row directly (avatar circle, sender, subject/snippet, time,
unread dot, account label) with zero QWidget instances created per row;
Qt only ever constructs paint calls for rows actually on screen. Model
resets are the only "rebuild" cost, and reselecting the previously
current row after a reset is done with the selection model's signals
blocked so it never re-triggers the read-marking/body-fetch side effects
in MainWindow - the exact same guard the old QTreeWidget code used.

Date-grouped section headers ("Today" / "Yesterday" / "Earlier") are
synthetic rows injected into the same flat model rather than a second
widget or a tree - they cost one extra dict per group (never per
message), carry no selectable flag, and the delegate paints them with a
distinct, shorter row height. Virtualization is untouched: Qt still only
ever asks the delegate to paint what's on screen.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui import theme as t
from app.ui.components.avatar import paint_avatar
from app.ui.svg_icon import tinted_pixmap

# Denser than before, following the reference's compact row rhythm while
# staying readable for two lines of real email metadata.
ROW_HEIGHT = 58
HEADER_HEIGHT = 30
_AVATAR_SIZE = 32
ROLE_MSG = Qt.ItemDataRole.UserRole


def format_time(ts: int) -> str:
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts)
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if dt.year == now.year:
        return dt.strftime("%d %b")
    return dt.strftime("%d %b %Y")


def _date_bucket(ts: int, today: date, yesterday: date) -> str:
    d = datetime.fromtimestamp(ts).date() if ts else today
    if d == today:
        return "Today"
    if d == yesterday:
        return "Yesterday"
    return "Earlier"


def _with_section_headers(rows: list[dict]) -> list[dict]:
    """Insert a lightweight {"is_header": True, "label": ...} marker before
    the first row of each date bucket. Rows already arrive newest-first
    (see db.list_emails' ORDER BY date_ts DESC), so a single linear pass
    is enough - no re-sorting.
    """
    if not rows:
        return rows
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    out: list[dict] = []
    last_bucket: str | None = None
    for row in rows:
        bucket = _date_bucket(row["date_ts"], today, yesterday)
        if bucket != last_bucket:
            out.append({"is_header": True, "label": bucket})
            last_bucket = bucket
        out.append(row)
    return out


class EmailListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        if role == ROLE_MSG:
            return self._rows[index.row()]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        base = super().flags(index)
        if index.isValid() and self._rows[index.row()].get("is_header"):
            return base & ~Qt.ItemFlag.ItemIsSelectable
        return base

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = _with_section_headers(rows)
        self.endResetModel()

    def index_of(self, email_id: int) -> QModelIndex:
        for i, row in enumerate(self._rows):
            if row.get("id") == email_id:
                return self.index(i, 0)
        return QModelIndex()


class EmailRowDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex) -> None:
        msg = index.data(ROLE_MSG)
        if msg is None:
            return super().paint(painter, option, index)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if msg.get("is_header"):
            self._paint_header(painter, option, msg["label"])
        else:
            self._paint_row(painter, option, msg)
        painter.restore()

    def _paint_header(self, painter: QPainter, option: QStyleOptionViewItem,
                      label: str) -> None:
        rect = option.rect.adjusted(t.SPACE_MD + 4, 0, -t.SPACE_MD, 0)
        painter.setFont(t.make_font("section_label"))
        painter.setPen(t.qcolor(t.TEXT_TERTIARY))
        painter.drawText(
            QRectF(rect), Qt.AlignmentFlag.AlignVCenter, label.upper()
        )

    def _paint_row(self, painter: QPainter, option: QStyleOptionViewItem,
                   msg: dict) -> None:
        rect = option.rect.adjusted(8, 3, -8, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            # A fill paired with a visible edge, not fill alone - the same
            # pairing the nav pills and section cards use for "selected",
            # so a glance at any part of the app reads it the same way.
            painter.setPen(QPen(t.qcolor(t.ACCENT), 1))
            painter.setBrush(t.qcolor(t.ACCENT_SOFT_BG))
            painter.drawRoundedRect(
                rect.adjusted(0, 0, -1, -1), t.RADIUS_MD, t.RADIUS_MD
            )
            # Left accent bar, the same "this one is active" cue the sidebar
            # nav pills and tabs use - a filled tint alone reads as hover at
            # a glance, the bar makes the selected row unambiguous.
            bar_h = rect.height() * 0.55
            bar = QRectF(
                rect.left(), rect.top() + (rect.height() - bar_h) / 2, 3, bar_h,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(t.qcolor(t.ACCENT))
            painter.drawRoundedRect(bar, 1.5, 1.5)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(t.qcolor(t.BG_HOVER))
            painter.drawRoundedRect(rect, t.RADIUS_MD, t.RADIUS_MD)

        unread = not msg["is_read"]
        pad = 10
        avatar_rect = QRectF(
            rect.left() + pad, rect.top() + (rect.height() - _AVATAR_SIZE) / 2,
            _AVATAR_SIZE, _AVATAR_SIZE,
        )
        sender_name = msg["sender_name"] or msg["sender_email"] or "(unknown)"
        paint_avatar(painter, avatar_rect, msg["sender_email"] or sender_name,
                    sender_name, msg["sender_email"])

        text_left = avatar_rect.right() + 12
        text_right = rect.right() - 10
        text_width = max(10, text_right - text_left)

        # -- top line: unread dot + sender name ... time
        top_y = rect.top() + 9
        name_font = t.make_font("sender" if unread else "sender_read")
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)

        time_text = format_time(msg["date_ts"])
        time_font = t.make_font("timestamp")
        time_width = QFontMetrics(time_font).horizontalAdvance(time_text)

        dot_space = 0
        if unread:
            dot_space = 10
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(t.qcolor(t.ACCENT))
            painter.drawEllipse(
                QRectF(text_left, top_y + fm.ascent() / 2 - 3, 6, 6)
            )

        name_rect = QRectF(
            text_left + dot_space, top_y, text_width - time_width - 10, fm.height()
        )
        painter.setPen(t.qcolor(t.TEXT_PRIMARY))
        elided_name = fm.elidedText(sender_name, Qt.TextElideMode.ElideRight,
                                    int(name_rect.width()))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elided_name)

        painter.setPen(t.qcolor(t.TEXT_TERTIARY))
        painter.setFont(time_font)
        painter.drawText(
            QRectF(text_right - time_width, top_y, time_width, fm.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, time_text,
        )

        # -- bottom line: real star/attachment icons, then subject - snippet
        bottom_y = top_y + fm.height() + 4
        subject = msg["subject"] or "(no subject)"
        subject_font = t.make_font("subject" if unread else "subject_read")
        fm2 = QFontMetrics(subject_font)

        icon_x = text_left
        icon_y = bottom_y + (fm2.height() - t.ICON_SIZE_ROW) / 2
        if msg["is_starred"]:
            painter.drawPixmap(
                int(icon_x), int(icon_y),
                tinted_pixmap("star_filled", t.ICON_SIZE_ROW, t.STARRED),
            )
            icon_x += t.ICON_SIZE_ROW + 4
        if msg["has_attachments"]:
            painter.drawPixmap(
                int(icon_x), int(icon_y),
                tinted_pixmap("attachment", t.ICON_SIZE_ROW, t.TEXT_TERTIARY),
            )
            icon_x += t.ICON_SIZE_ROW + 5

        text_start = icon_x
        combined = subject
        if msg.get("snippet"):
            combined += "  —  " + msg["snippet"]
        painter.setPen(t.qcolor(t.TEXT_PRIMARY if unread else t.TEXT_SECONDARY))
        painter.setFont(subject_font)
        elided_subject = fm2.elidedText(
            combined, Qt.TextElideMode.ElideRight, int(text_right - text_start)
        )
        painter.drawText(
            QRectF(text_start, bottom_y, text_right - text_start, fm2.height()),
            Qt.AlignmentFlag.AlignVCenter, elided_subject,
        )

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        msg = index.data(ROLE_MSG)
        height = HEADER_HEIGHT if msg and msg.get("is_header") else ROW_HEIGHT
        return QSize(option.rect.width(), height)


class EmailListView(QListView):
    email_selected = Signal(int)
    context_menu_requested = Signal(int, object)  # email_id, global QPoint

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("emailList")
        self._model = EmailListModel(self)
        self.setModel(self._model)
        self.setItemDelegate(EmailRowDelegate(self))
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)  # enables hover state in the delegate
        self.setSpacing(0)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    # ------------------------------------------------------------------ data

    def set_rows(self, rows: list[dict], keep_selected_id: int | None = None) -> None:
        self._model.set_rows(rows)
        if keep_selected_id is not None:
            self._select_silently(keep_selected_id)

    def row_count(self) -> int:
        """Real message rows only - excludes synthetic date-section headers."""
        return sum(1 for r in self._model._rows if not r.get("is_header"))

    def selected_email_id(self) -> int | None:
        indexes = self.selectionModel().selectedIndexes()
        if not indexes:
            return None
        msg = indexes[0].data(ROLE_MSG)
        return msg.get("id") if msg else None

    def select_email(self, email_id: int) -> None:
        """User-visible selection change - fires email_selected normally."""
        index = self._model.index_of(email_id)
        if index.isValid():
            self.setCurrentIndex(index)

    def _select_silently(self, email_id: int) -> None:
        index = self._model.index_of(email_id)
        if not index.isValid():
            return
        self.selectionModel().blockSignals(True)
        self.setCurrentIndex(index)
        self.selectionModel().blockSignals(False)

    # --------------------------------------------------------------- signals

    def _on_selection_changed(self, *_args) -> None:
        email_id = self.selected_email_id()
        if email_id is not None:
            self.email_selected.emit(email_id)

    def _on_context_menu(self, pos) -> None:
        index = self.indexAt(pos)
        if not index.isValid():
            return
        msg = index.data(ROLE_MSG)
        if msg and not msg.get("is_header"):
            self.context_menu_requested.emit(msg["id"], self.viewport().mapToGlobal(pos))

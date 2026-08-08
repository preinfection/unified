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
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui import theme as t
from app.ui.components.avatar import paint_avatar

ROW_HEIGHT = 60
_AVATAR_SIZE = 34
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

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def index_of(self, email_id: int) -> QModelIndex:
        for i, row in enumerate(self._rows):
            if row["id"] == email_id:
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

        rect = option.rect.adjusted(6, 3, -6, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(t.qcolor(t.BG_SELECTED))
            painter.drawRoundedRect(rect, 8, 8)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(t.qcolor(t.BG_HOVER))
            painter.drawRoundedRect(rect, 8, 8)

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
        name_font = QFont(painter.font())
        name_font.setBold(unread)
        name_font.setPixelSize(13)
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)

        time_text = format_time(msg["date_ts"])
        time_width = fm.horizontalAdvance(time_text)

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
        painter.setPen(t.qcolor(t.TEXT_PRIMARY if unread else t.TEXT_PRIMARY))
        elided_name = fm.elidedText(sender_name, Qt.TextElideMode.ElideRight,
                                    int(name_rect.width()))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elided_name)

        painter.setPen(t.qcolor(t.TEXT_TERTIARY))
        time_font = QFont(painter.font())
        time_font.setBold(False)
        time_font.setPixelSize(12)
        painter.setFont(time_font)
        painter.drawText(
            QRectF(text_right - time_width, top_y, time_width, fm.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, time_text,
        )

        # -- bottom line: subject - snippet, plus attachment/star glyphs
        bottom_y = top_y + fm.height() + 4
        subject = msg["subject"] or "(no subject)"
        prefix = ""
        if msg["is_starred"]:
            prefix += "★ "  # star
        if msg["has_attachments"]:
            prefix += "\U0001F4CE "  # paperclip
        subject_font = QFont(painter.font())
        subject_font.setBold(unread)
        subject_font.setPixelSize(12)
        painter.setFont(subject_font)
        fm2 = QFontMetrics(subject_font)
        combined = f"{prefix}{subject}"
        if msg.get("snippet"):
            combined += "  –  " + msg["snippet"]
        painter.setPen(t.qcolor(t.TEXT_PRIMARY if unread else t.TEXT_SECONDARY))
        elided_subject = fm2.elidedText(
            combined, Qt.TextElideMode.ElideRight, int(text_width)
        )
        painter.drawText(
            QRectF(text_left, bottom_y, text_width, fm2.height()),
            Qt.AlignmentFlag.AlignVCenter, elided_subject,
        )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), ROW_HEIGHT)


class EmailListView(QListView):
    email_selected = Signal(int)
    context_menu_requested = Signal(int, object)  # email_id, global QPoint

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("emailList")
        self._model = EmailListModel(self)
        self.setModel(self._model)
        self.setItemDelegate(EmailRowDelegate(self))
        self.setUniformItemSizes(True)
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
        return self._model.rowCount()

    def selected_email_id(self) -> int | None:
        indexes = self.selectionModel().selectedIndexes()
        if not indexes:
            return None
        msg = indexes[0].data(ROLE_MSG)
        return msg["id"] if msg else None

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
        if msg:
            self.context_menu_requested.emit(msg["id"], self.viewport().mapToGlobal(pos))

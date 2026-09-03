"""The message list: a virtualized QListView with a painted row delegate.

This is the surface with real performance stakes - cached mailboxes here
run past 10,000 messages - so there is no widget per row. A delegate
paints each visible row directly and Qt only ever asks it to paint what
is on screen. Model resets are the only rebuild cost, and reselecting the
previously current row after a reset happens with the selection model's
signals blocked so it never re-triggers read-marking or a body fetch.

The row itself is the redesign's most-considered piece of layout:

    ┌──┬────┬──────────────────────────────────────────┐
    │● │ AV │ Sender name                        14:32  │
    │  │    │ Subject line                        ★ ⏎  │
    │  │    │ Preview text, one line, elided…  account  │
    └──┴────┴──────────────────────────────────────────┘

* The unread dot lives in its own fixed gutter, so read and unread rows
  align on the same left edge. (Previously the dot was inline, which
  shifted every unread sender name 10px right and made a mixed list look
  ragged down the middle.)
* Unread is carried by *three* signals - the dot, a heavier sender
  weight, and full-strength text - so it survives both a glance and a
  color-vision difference. Read rows drop to secondary text rather than
  changing hue.
* Subject and preview are separate lines rather than one string joined by
  a dash: the dash version elides the preview and the subject together,
  so a long subject silently ate the preview.
* The account address appears on the third line only when more than one
  account is in view. In a unified inbox, "which of my addresses received
  this" is information; in a single-account view it is noise.
* Selection pairs a tinted fill with a leading accent bar. Fill alone at a
  glance is indistinguishable from hover, which is the difference between
  "the pointer is here" and "this is what you are reading".

Date-group headers are synthetic rows in the same flat model rather than
a second widget or a tree: one extra dict per group, never per message,
and virtualization is untouched.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from app.ui import theme as t
from app.ui.components.avatar import paint_avatar
from app.ui.svg_icon import tinted_pixmap

# The default density's row height, kept as a module constant because the
# delegate, the skeleton loader and the tests all need to agree on it.
# `t.row_height()` is the live value once the user picks a density.
ROW_HEIGHT = t.DENSITY_METRICS[t.DENSITY_DEFAULT][0]
HEADER_HEIGHT = t.GROUP_HEADER_HEIGHT
COMPACT_ROW_HEIGHT = t.DENSITY_METRICS[t.DENSITY_COMPACT][0]

_AVATAR = t.AVATAR_MD
_GUTTER = 16          # unread-dot column; keeps read/unread rows aligned
_DOT = 7
_PAD_X = 10
_ICON = t.ICON_XS + 1

ROLE_MSG = Qt.ItemDataRole.UserRole


def format_time(ts: int) -> str:
    """Timestamps shorten as they age - the closer a message is, the more
    precisely a person wants it placed."""
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts)
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if (now.date() - dt.date()).days == 1:
        return "Yesterday"
    if dt.year == now.year:
        return dt.strftime("%d %b")
    return dt.strftime("%d %b %Y")


def format_full_time(ts: int) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%a, %d %b %Y at %H:%M")


def _date_bucket(ts: int, today: date) -> str:
    d = datetime.fromtimestamp(ts).date() if ts else today
    delta = (today - d).days
    if delta <= 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if delta < 7:
        return "This week"
    if delta < 30:
        return "This month"
    if d.year == today.year:
        return "Earlier this year"
    return "Older"


def _with_section_headers(rows: list[dict]) -> list[dict]:
    """Insert a {"is_header": True, ...} marker before the first row of
    each date bucket. Rows arrive newest-first (db.list_emails orders by
    date_ts DESC), so one linear pass is enough - no re-sorting."""
    if not rows:
        return rows
    today = datetime.now().date()
    out: list[dict] = []
    last_bucket: str | None = None
    for row in rows:
        bucket = _date_bucket(row["date_ts"], today)
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
        row = self._rows[index.row()]
        if role == ROLE_MSG:
            return row
        if role == Qt.ItemDataRole.AccessibleTextRole:
            if row.get("is_header"):
                return row["label"]
            state = "Unread" if not row["is_read"] else "Read"
            return (
                f"{state} message from "
                f"{row['sender_name'] or row['sender_email']}, "
                f"subject {row['subject'] or 'no subject'}, "
                f"{format_full_time(row['date_ts'])}"
            )
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        base = super().flags(index)
        if index.isValid() and self._rows[index.row()].get("is_header"):
            return base & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.show_account = False

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

    # ------------------------------------------------------------ header

    def _paint_header(self, painter: QPainter, option: QStyleOptionViewItem,
                      label: str) -> None:
        rect = option.rect
        font = t.make_font("overline")
        metrics = QFontMetrics(font)
        painter.setFont(font)
        painter.setPen(t.qcolor(t.TEXT_TERTIARY))
        text = label.upper()
        text_width = metrics.horizontalAdvance(text)
        x = rect.left() + _PAD_X + 2
        baseline_rect = QRectF(x, rect.top(), text_width, rect.height())
        painter.drawText(baseline_rect, Qt.AlignmentFlag.AlignVCenter, text)

        # A hairline running from the label to the right edge ties the
        # group together without drawing a full-width divider that would
        # read as a table rule.
        line_y = rect.center().y() + 1
        painter.setPen(QPen(t.qcolor(t.BORDER_SUBTLE), 1))
        painter.drawLine(
            int(x + text_width + t.SPACE_MD), int(line_y),
            int(rect.right() - _PAD_X), int(line_y),
        )

    # --------------------------------------------------------------- row

    def _paint_row(self, painter: QPainter, option: QStyleOptionViewItem,
                   msg: dict) -> None:
        rect = option.rect.adjusted(4, 1, -4, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        unread = not msg["is_read"]
        lines = t.row_lines()

        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(t.qcolor(t.BG_SELECTED))
            painter.drawRoundedRect(QRectF(rect), t.RADIUS_SM, t.RADIUS_SM)
            bar_h = rect.height() * 0.62
            painter.setBrush(t.qcolor(t.ACCENT))
            painter.drawRoundedRect(
                QRectF(rect.left(), rect.top() + (rect.height() - bar_h) / 2, 3, bar_h),
                1.5, 1.5,
            )
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(t.qcolor(t.BG_HOVER))
            painter.drawRoundedRect(QRectF(rect), t.RADIUS_SM, t.RADIUS_SM)

        # -- unread gutter (fixed width, so every row's avatar aligns)
        gutter_x = rect.left() + _PAD_X - 2
        if unread:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(t.qcolor(t.UNREAD))
            painter.drawEllipse(
                QRectF(
                    gutter_x + (_GUTTER - _DOT) / 2,
                    rect.center().y() - _DOT / 2 + 0.5,
                    _DOT, _DOT,
                )
            )

        # -- avatar
        avatar_x = gutter_x + _GUTTER
        avatar_rect = QRectF(
            avatar_x, rect.top() + (rect.height() - _AVATAR) / 2, _AVATAR, _AVATAR
        )
        sender_name = msg["sender_name"] or msg["sender_email"] or "(unknown)"
        paint_avatar(
            painter, avatar_rect, msg["sender_email"] or sender_name,
            sender_name, msg["sender_email"], dimmed=not unread,
        )

        text_left = avatar_rect.right() + t.SPACE_LG
        text_right = rect.right() - _PAD_X
        if text_right - text_left < 40:
            return  # pane too narrow to render anything honestly

        # -- line 1: sender, then timestamp hard-right
        name_font = t.make_font("sender" if unread else "sender_read")
        name_metrics = QFontMetrics(name_font)
        time_font = t.make_font("timestamp")
        time_metrics = QFontMetrics(time_font)
        time_text = format_time(msg["date_ts"])
        time_width = time_metrics.horizontalAdvance(time_text)

        line_h = name_metrics.height()
        block_h = line_h + (line_h - 2) + (line_h - 3 if lines >= 3 else 0)
        top = rect.top() + (rect.height() - block_h) / 2

        painter.setFont(name_font)
        painter.setPen(t.qcolor(t.TEXT_PRIMARY if unread else t.TEXT_SECONDARY))
        painter.drawText(
            QRectF(text_left, top, text_right - text_left - time_width - t.SPACE_MD,
                   line_h),
            Qt.AlignmentFlag.AlignVCenter,
            name_metrics.elidedText(
                sender_name, Qt.TextElideMode.ElideRight,
                int(text_right - text_left - time_width - t.SPACE_MD),
            ),
        )
        painter.setFont(time_font)
        painter.setPen(t.qcolor(t.TEXT_TERTIARY))
        painter.drawText(
            QRectF(text_right - time_width, top, time_width, line_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, time_text,
        )

        # -- line 2: subject, with star/attachment pinned right
        subject_font = t.make_font("subject" if unread else "subject_read")
        subject_metrics = QFontMetrics(subject_font)
        subject_top = top + line_h
        icons_width = 0.0
        icon_x = text_right
        if msg["has_attachments"]:
            icon_x -= _ICON
            painter.drawPixmap(
                int(icon_x), int(subject_top + (subject_metrics.height() - _ICON) / 2),
                tinted_pixmap("attachment", _ICON, t.TEXT_TERTIARY),
            )
            icons_width += _ICON + t.SPACE_XS
            icon_x -= t.SPACE_XS
        if msg["is_starred"]:
            icon_x -= _ICON
            painter.drawPixmap(
                int(icon_x), int(subject_top + (subject_metrics.height() - _ICON) / 2),
                tinted_pixmap("star_filled", _ICON, t.STARRED),
            )
            icons_width += _ICON + t.SPACE_XS

        subject_width = int(text_right - text_left - icons_width)
        painter.setFont(subject_font)
        painter.setPen(t.qcolor(t.TEXT_PRIMARY if unread else t.TEXT_SECONDARY))
        painter.drawText(
            QRectF(text_left, subject_top, subject_width, subject_metrics.height()),
            Qt.AlignmentFlag.AlignVCenter,
            subject_metrics.elidedText(
                msg["subject"] or "(no subject)", Qt.TextElideMode.ElideRight,
                max(20, subject_width),
            ),
        )

        if lines < 3:
            return

        # -- line 3: preview, with the receiving account when it matters
        preview_font = t.make_font("preview")
        preview_metrics = QFontMetrics(preview_font)
        preview_top = subject_top + subject_metrics.height()
        account_width = 0.0
        if self.show_account and msg.get("account_email"):
            account_text = msg["account_email"]
            account_width = min(
                preview_metrics.horizontalAdvance(account_text),
                (text_right - text_left) * 0.38,
            )
            painter.setFont(preview_font)
            painter.setPen(t.qcolor(t.TEXT_TERTIARY))
            painter.drawText(
                QRectF(text_right - account_width, preview_top, account_width,
                       preview_metrics.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                preview_metrics.elidedText(
                    account_text, Qt.TextElideMode.ElideLeft, int(account_width)
                ),
            )
            account_width += t.SPACE_LG

        preview_width = int(text_right - text_left - account_width)
        snippet = (msg.get("snippet") or "").replace("\n", " ").strip()
        if snippet and preview_width > 20:
            painter.setFont(preview_font)
            painter.setPen(t.qcolor(t.TEXT_TERTIARY))
            painter.drawText(
                QRectF(text_left, preview_top, preview_width,
                       preview_metrics.height()),
                Qt.AlignmentFlag.AlignVCenter,
                preview_metrics.elidedText(
                    snippet, Qt.TextElideMode.ElideRight, preview_width
                ),
            )

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        msg = index.data(ROLE_MSG)
        height = HEADER_HEIGHT if msg and msg.get("is_header") else t.row_height()
        return QSize(option.rect.width(), height)


class EmailListView(QListView):
    email_selected = Signal(int)
    email_activated = Signal(int)                # Enter / double-click
    context_menu_requested = Signal(int, object)  # email_id, global QPoint
    reached_end = Signal()                        # scrolled to the bottom

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("emailList")
        self._model = EmailListModel(self)
        self.setModel(self._model)
        self._delegate = EmailRowDelegate(self)
        self.setItemDelegate(self._delegate)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)  # enables the delegate's hover state
        self.setSpacing(0)
        self.setUniformItemSizes(False)
        self.setFrameShape(QListView.Shape.NoFrame)
        # Rows elide their own text to the viewport width, so a horizontal
        # scrollbar can only ever be a layout bug made visible.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setAccessibleName("Message list")
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.doubleClicked.connect(self._on_double_clicked)
        self.verticalScrollBar().valueChanged.connect(self._on_scrolled)
        t.theme_manager.density_changed.connect(self._on_density_changed)

    # ------------------------------------------------------------------ data

    def set_rows(self, rows: list[dict], keep_selected_id: int | None = None) -> None:
        self._model.set_rows(rows)
        if keep_selected_id is not None:
            self._select_silently(keep_selected_id)

    def set_show_account(self, show: bool) -> None:
        """Show each row's receiving account - on in a unified view,
        off when the list is already scoped to one account."""
        if self._delegate.show_account != show:
            self._delegate.show_account = show
            self.viewport().update()

    def row_count(self) -> int:
        """Real message rows only - excludes synthetic date headers."""
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
            self.scrollTo(index, QListView.ScrollHint.EnsureVisible)

    def _select_silently(self, email_id: int) -> None:
        index = self._model.index_of(email_id)
        if not index.isValid():
            return
        self.selectionModel().blockSignals(True)
        self.setCurrentIndex(index)
        self.selectionModel().blockSignals(False)

    def move_selection(self, delta: int) -> None:
        """Keyboard j/k and arrow navigation, skipping date headers."""
        rows = self._model._rows
        if not rows:
            return
        current = self.currentIndex().row()
        step = 1 if delta > 0 else -1
        position = current if current >= 0 else (-1 if step > 0 else len(rows))
        for _ in range(abs(delta) or 1):
            position += step
            while 0 <= position < len(rows) and rows[position].get("is_header"):
                position += step
        if 0 <= position < len(rows):
            index = self._model.index(position, 0)
            self.setCurrentIndex(index)
            self.scrollTo(index, QListView.ScrollHint.EnsureVisible)

    # --------------------------------------------------------------- signals

    def _on_density_changed(self) -> None:
        # Row geometry comes from the delegate's sizeHint, so Qt has to be
        # told the hints are stale; a plain repaint would keep old heights.
        self._delegate.sizeHintChanged.emit(QModelIndex())
        self.scheduleDelayedItemsLayout()

    def _on_selection_changed(self, *_args) -> None:
        email_id = self.selected_email_id()
        if email_id is not None:
            self.email_selected.emit(email_id)

    def _on_double_clicked(self, index) -> None:
        msg = index.data(ROLE_MSG)
        if msg and not msg.get("is_header"):
            self.email_activated.emit(msg["id"])

    def _on_scrolled(self, value: int) -> None:
        bar = self.verticalScrollBar()
        if bar.maximum() and value >= bar.maximum() - 8:
            self.reached_end.emit()

    def _on_context_menu(self, pos) -> None:
        index = self.indexAt(pos)
        if not index.isValid():
            return
        msg = index.data(ROLE_MSG)
        if msg and not msg.get("is_header"):
            self.context_menu_requested.emit(
                msg["id"], self.viewport().mapToGlobal(pos)
            )

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            email_id = self.selected_email_id()
            if email_id is not None:
                self.email_activated.emit(email_id)
                event.accept()
                return
        if key in (Qt.Key.Key_J, Qt.Key.Key_K) and not event.modifiers():
            self.move_selection(1 if key == Qt.Key.Key_J else -1)
            event.accept()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            # Qt's own arrow handling would land on a date header, which
            # is not selectable, and stall there.
            self.move_selection(1 if key == Qt.Key.Key_Down else -1)
            event.accept()
            return
        super().keyPressEvent(event)

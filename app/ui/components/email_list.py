"""Virtualized email list: QAbstractListModel + QStyledItemDelegate +
QListView, instead of one QTreeWidgetItem per row.

This is the one part of the UI with real performance stakes: mailboxes
here run to 10,000+ cached messages. A delegate paints each visible row
directly with zero QWidget instances per row; Qt only ever constructs
paint calls for rows actually on screen. Model resets are the only
"rebuild" cost, and reselecting the previously current row after a reset
is done with the selection model's signals blocked so it never re-triggers
the read-marking/body-fetch side effects in MainWindow.

Date-grouped headers ("Today" / "Yesterday" / "Earlier") are synthetic
rows in the same flat model rather than a second widget or a tree: one
extra dict per group, never per message, no selectable flag, and a
distinct painted treatment. Virtualization is untouched.

=========================================================================
THE ROW IS THREE LINES NOW, AND THAT IS THE BIGGEST CHANGE IN THIS FILE

It used to be two, with the subject and the preview concatenated into one
string joined by a separator:

    Ada Lovelace                                             16:05
    ★ Re: the engine notes  ·  I have finished the appendix...

Two things are wrong with that. The subject and the snippet are different
kinds of information competing inside a single line, so the eye cannot
skip the snippet when scanning subjects. And the elision is applied to the
JOINED string, which means a long subject eats the entire preview and a
short one leaves the preview truncated mid-word at a position that depends
on the subject's length. Scanning a list is the single most common thing
anyone does in a mail client, and this was the layout making it slower.

Three lines, each with one job:

    ●  Ada Lovelace                                    16:05
       Re: the engine notes                              ★ ⏵
       I have finished the appendix and it runs to three...

Every real desktop client converges on this, which is a signal rather than
a coincidence. Each line elides against its own width.

QUICK ACTIONS ON HOVER. Star and delete appear at the right of a hovered
row, over the timestamp. Painted by the delegate and hit-tested by the
view (see EmailListView.mouseMoveEvent) rather than being real widgets,
because real widgets per row would end the virtualization that makes this
list fast at 10,000 messages.

DENSITY. Two row heights, comfortable and compact, because a mailbox with
40 messages and one with 4,000 want different things and the difference is
one token, not a second layout.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import (
    QEvent, QModelIndex, QPoint, QRect, QRectF, QSize, Qt, Property, Signal,
)
from PySide6.QtCore import QAbstractListModel
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui import theme as t
from app.ui.components.avatar import paint_avatar
from app.ui.components.primitives import paint_edge_fade
from app.ui.svg_icon import tinted_pixmap

ROLE_MSG = Qt.ItemDataRole.UserRole

# Kept as module constants because MainWindow and the tests read them.
ROW_HEIGHT = t.ROW_HEIGHT_COMFORTABLE
HEADER_HEIGHT = t.ROW_GROUP_HEIGHT
_AVATAR_SIZE = 34
_AVATAR_SIZE_COMPACT = 26

# Hover quick actions, right to left from the row's right edge.
_ACTION_SIZE = 26
_ACTION_ICON = 15
ACTION_STAR = "star"
ACTION_DELETE = "delete"


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
    """Insert a {"is_header": True, "label": ...} marker before the first
    row of each date bucket. Rows arrive newest-first (db.list_emails
    ORDER BY date_ts DESC), so one linear pass is enough."""
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
        row = self._rows[index.row()]
        if role == ROLE_MSG:
            return row
        if role == Qt.ItemDataRole.AccessibleTextRole:
            # What a screen reader announces. A custom-painted row is
            # otherwise silent, because there is no text in the item model.
            if row.get("is_header"):
                return row["label"]
            state = "unread" if not row.get("is_read") else "read"
            return (f"{state} message from "
                    f"{row.get('sender_name') or row.get('sender_email') or 'unknown'}, "
                    f"subject {row.get('subject') or 'no subject'}, "
                    f"{format_time(row.get('date_ts') or 0)}")
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
    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self._compact = compact
        # Which row the pointer is over, and where in it. The view keeps
        # these current; the delegate only reads them.
        self.hover_row: int = -1
        self.hover_action: str = ""

    def set_compact(self, compact: bool) -> None:
        self._compact = compact

    # ---------------------------------------------------------- geometry

    def row_height(self) -> int:
        return t.ROW_HEIGHT_COMPACT if self._compact else t.ROW_HEIGHT_COMFORTABLE

    def action_rects(self, rect: QRect) -> dict[str, QRect]:
        """Hit boxes for the hover actions, right-aligned.

        Public because the VIEW does the hit-testing: a delegate has no
        mouse events of its own, so the two have to agree on this geometry
        and there must be exactly one definition of it.
        """
        top = rect.top() + (rect.height() - _ACTION_SIZE) // 2
        right = rect.right() - t.SPACE_SM
        boxes: dict[str, QRect] = {}
        for name in (ACTION_DELETE, ACTION_STAR):
            right -= _ACTION_SIZE
            boxes[name] = QRect(right, top, _ACTION_SIZE, _ACTION_SIZE)
            right -= t.SPACE_XXS
        return boxes

    # ------------------------------------------------------------- paint

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex) -> None:
        msg = index.data(ROLE_MSG)
        if msg is None:
            return super().paint(painter, option, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # The reveal offset is applied HERE rather than on the view: the
        # delegate is handed the painter that actually draws a row, so a
        # translate is one line and costs nothing, whereas nudging the
        # QListView itself would be undone by the splitter on the next
        # layout pass. See motion.reveal for why the rise is opt-in.
        view = self.parent()
        offset = getattr(view, "_reveal_offset", 0.0)
        if offset:
            painter.translate(0.0, offset)
        if msg.get("is_header"):
            self._paint_header(painter, option, msg["label"])
        else:
            self._paint_row(painter, option, index, msg)
        painter.restore()

    def _paint_header(self, painter: QPainter, option: QStyleOptionViewItem,
                      label: str) -> None:
        """A date group break: a small caps label, and a hairline that runs
        from the end of it to the edge of the list. A rule is a real
        typographic device for "a group starts here"; a colored tick beside
        the words, which is what this used to be, is ornament."""
        rect = option.rect.adjusted(t.SPACE_MD, 0, -t.SPACE_MD, 0)
        font = t.make_font("section_label")
        painter.setFont(font)
        painter.setPen(t.qcolor(t.TEXT_TERTIARY))
        text = label.upper()
        width = QFontMetrics(font).horizontalAdvance(text)
        baseline = QRectF(rect)
        painter.drawText(baseline, Qt.AlignmentFlag.AlignVCenter, text)

        line_x = rect.left() + width + t.SPACE_SM
        y = rect.center().y() + 1
        if line_x < rect.right():
            painter.setPen(t.qcolor(t.BORDER))
            painter.drawLine(line_x, y, rect.right(), y)

    def _paint_row(self, painter: QPainter, option: QStyleOptionViewItem,
                   index: QModelIndex, msg: dict) -> None:
        rect = option.rect.adjusted(t.SPACE_SM, 1, -t.SPACE_SM, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = index.row() == self.hover_row
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)

        # SELECTION IS ELEVATION, AND IT IS ONE CUE. This used to paint an
        # accent fill, an accent border AND a 3px accent bar down the left
        # edge: three devices for one boolean, one of them the side-stripe
        # pattern the app no longer uses anywhere.
        painter.setPen(Qt.PenStyle.NoPen)
        if selected:
            painter.setBrush(t.qcolor(t.BG_SELECTED))
            painter.drawRoundedRect(rect, t.RADIUS_SM, t.RADIUS_SM)
        elif hovered:
            painter.setBrush(t.qcolor(t.WASH_HOVER))
            painter.drawRoundedRect(rect, t.RADIUS_SM, t.RADIUS_SM)

        # Keyboard focus is drawn even when the row is also selected: the
        # two are different (you can move focus through a list without
        # changing the selection) and a keyboard user has to see which row
        # will act on Enter.
        if focused and self.parent() is not None and self.parent().hasFocus():
            painter.setPen(t.qcolor(t.FOCUS_RING))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), t.RADIUS_SM, t.RADIUS_SM
            )
            painter.setPen(Qt.PenStyle.NoPen)

        unread = not msg["is_read"]
        compact = self._compact
        avatar_size = _AVATAR_SIZE_COMPACT if compact else _AVATAR_SIZE

        # ---- unread dot, in its own narrow column so the avatars stay in
        # a straight line whether or not a row is unread.
        dot_col = t.SPACE_SM + 6
        if unread:
            painter.setBrush(t.qcolor(t.TEXT_PRIMARY))
            painter.drawEllipse(
                QRectF(rect.left() + t.SPACE_XS, rect.center().y() - 3, 6, 6)
            )

        avatar_x = rect.left() + dot_col
        avatar_rect = QRectF(
            avatar_x, rect.top() + (rect.height() - avatar_size) / 2,
            avatar_size, avatar_size,
        )
        sender_name = msg["sender_name"] or msg["sender_email"] or "(unknown)"
        paint_avatar(painter, avatar_rect, msg["sender_email"] or sender_name,
                     sender_name, msg["sender_email"])

        text_left = avatar_rect.right() + t.SPACE_MD
        text_right = rect.right() - t.SPACE_MD
        if text_right <= text_left:
            return

        # ---- line 1: sender, then attachment mark and time on the right
        name_font = t.make_font("sender" if unread else "sender_read")
        fm_name = QFontMetrics(name_font)
        time_font = t.make_font("timestamp")
        fm_time = QFontMetrics(time_font)

        line_h = fm_name.height()
        if compact:
            # Two lines in compact: sender + time, then subject. The
            # snippet is what goes, because it is the least information per
            # pixel of the three.
            block_h = line_h + QFontMetrics(t.make_font("subject")).height() + 2
        else:
            block_h = (line_h
                       + QFontMetrics(t.make_font("subject")).height()
                       + QFontMetrics(t.make_font("preview")).height() + 6)
        y = rect.top() + (rect.height() - block_h) / 2

        time_text = format_time(msg["date_ts"])
        time_w = fm_time.horizontalAdvance(time_text)

        # The quick actions occupy the same corner as the timestamp, so the
        # timestamp gives way while they are showing rather than the two
        # overlapping.
        show_actions = hovered and not compact
        right_edge = text_right - (
            (_ACTION_SIZE * 2 + t.SPACE_XXS) if show_actions else 0
        )

        att_w = 0
        if msg["has_attachments"]:
            att_w = t.ICON_SIZE_ROW + t.SPACE_XS
            painter.drawPixmap(
                int(right_edge - time_w - att_w),
                int(y + (line_h - t.ICON_SIZE_ROW) / 2),
                tinted_pixmap("attachment", t.ICON_SIZE_ROW, t.TEXT_TERTIARY),
            )

        if not show_actions and time_text:
            painter.setPen(t.qcolor(t.TEXT_TERTIARY))
            painter.setFont(time_font)
            painter.drawText(
                QRectF(right_edge - time_w, y, time_w, line_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                time_text,
            )

        name_w = max(10, right_edge - time_w - att_w - t.SPACE_SM - text_left)
        painter.setPen(t.qcolor(t.TEXT_PRIMARY if unread else t.TEXT_SECONDARY))
        painter.setFont(name_font)
        painter.drawText(
            QRectF(text_left, y, name_w, line_h),
            Qt.AlignmentFlag.AlignVCenter,
            fm_name.elidedText(sender_name, Qt.TextElideMode.ElideRight, int(name_w)),
        )

        # ---- line 2: subject, with the star sitting after it
        y += line_h + 2
        subject_font = t.make_font("subject" if unread else "subject_read")
        fm_subj = QFontMetrics(subject_font)
        subj_h = fm_subj.height()
        star_w = 0
        if msg["is_starred"]:
            star_w = t.ICON_SIZE_ROW + t.SPACE_XS
        subj_w = max(10, text_right - text_left - star_w)
        painter.setPen(t.qcolor(t.TEXT_PRIMARY if unread else t.TEXT_SECONDARY))
        painter.setFont(subject_font)
        subject = msg["subject"] or "(no subject)"
        drawn = fm_subj.elidedText(subject, Qt.TextElideMode.ElideRight, int(subj_w))
        painter.drawText(
            QRectF(text_left, y, subj_w, subj_h),
            Qt.AlignmentFlag.AlignVCenter, drawn,
        )
        if msg["is_starred"]:
            painter.drawPixmap(
                int(text_left + fm_subj.horizontalAdvance(drawn) + t.SPACE_XS),
                int(y + (subj_h - t.ICON_SIZE_ROW) / 2),
                tinted_pixmap("star_filled", t.ICON_SIZE_ROW, t.STARRED),
            )

        # ---- line 3: snippet (comfortable density only)
        if not compact and msg.get("snippet"):
            y += subj_h + 2
            preview_font = t.make_font("preview")
            fm_prev = QFontMetrics(preview_font)
            painter.setPen(t.qcolor(t.TEXT_TERTIARY))
            painter.setFont(preview_font)
            width = max(10, text_right - text_left)
            painter.drawText(
                QRectF(text_left, y, width, fm_prev.height()),
                Qt.AlignmentFlag.AlignVCenter,
                fm_prev.elidedText(msg["snippet"], Qt.TextElideMode.ElideRight,
                                   int(width)),
            )

        # ---- hover quick actions
        if show_actions:
            for name, box in self.action_rects(rect).items():
                active = self.hover_action == name
                if active:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(t.qcolor(t.BG_SELECTED))
                    painter.drawRoundedRect(box, t.RADIUS_XS, t.RADIUS_XS)
                if name == ACTION_STAR:
                    icon = "star_filled" if msg["is_starred"] else "star_outline"
                    color = t.STARRED if msg["is_starred"] else (
                        t.TEXT_PRIMARY if active else t.TEXT_TERTIARY)
                else:
                    icon = "trash"
                    color = t.DESTRUCTIVE if active else t.TEXT_TERTIARY
                painter.drawPixmap(
                    box.x() + (box.width() - _ACTION_ICON) // 2,
                    box.y() + (box.height() - _ACTION_ICON) // 2,
                    tinted_pixmap(icon, _ACTION_ICON, color),
                )

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        """Row height, and a width that is the VIEWPORT's, not the view's.

        THIS WAS A REAL CLIPPING BUG, not a tidy-up. It used to return
        option.rect.width(), and during a layout pass Qt hands the delegate
        an option whose rect is the WIDGET width - 380px on a narrow window
        - while the visible viewport is 366px, because the vertical
        scrollbar has taken 14 of them. Rows were therefore laid out 14px
        wider than the space they are drawn into, which did two things:

          * a horizontal scrollbar appeared under a message list, which
            should never happen and which nothing in the design allows for;
          * every line elided against 380px and was then hard-clipped by
            the viewport at 366, so subjects and snippets were cut
            mid-word with no ellipsis - the truncation looked like a
            rendering fault rather than an elision.

        Measured, not inferred: viewport().width() reported 366 against a
        visualRect() of 380 on a 380px-wide view.

        The view's own horizontal scrollbar is off (see EmailListView), so
        the viewport width is also the final width and there is no
        feedback loop between the two.
        """
        view = self.parent()
        width = option.rect.width()
        if isinstance(view, QListView):
            width = view.viewport().width()
        if msg := index.data(ROLE_MSG):
            if msg.get("is_header"):
                return QSize(width, t.ROW_GROUP_HEIGHT)
        return QSize(width, self.row_height())


class EmailListView(QListView):
    email_selected = Signal(int)
    context_menu_requested = Signal(int, object)  # email_id, global QPoint
    star_toggled = Signal(int)                    # email_id
    delete_requested = Signal(int)                # email_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("emailList")
        self._model = EmailListModel(self)
        self.setModel(self._model)
        self._delegate = EmailRowDelegate(self)
        self.setItemDelegate(self._delegate)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        # A MESSAGE LIST NEVER SCROLLS SIDEWAYS. Every line in a row elides
        # against the row's own width, so there is by construction nothing
        # to the right to scroll to; a horizontal bar here only ever meant
        # the rows had been laid out wider than the viewport (see
        # EmailRowDelegate.sizeHint), and it stole height from the list to
        # show a control that could not help.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.setSpacing(0)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setUniformItemSizes(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._reveal_offset = 0.0

    # -------------------------------------------------------------- reveal

    def _get_reveal_offset(self) -> float:
        return self._reveal_offset

    def _set_reveal_offset(self, value: float) -> None:
        self._reveal_offset = float(value)
        self.viewport().update()

    # Declared so motion.reveal() can find it - see the note there about
    # why the rise is opt-in. The list shifts its OWN painting rather than
    # being moved, because a QListView is owned by a splitter and moving
    # it would simply be undone on the next layout pass.
    revealOffset = Property(float, _get_reveal_offset, _set_reveal_offset)

    # ------------------------------------------------------------- density

    def set_compact(self, compact: bool) -> None:
        self._delegate.set_compact(compact)
        # A size-hint change needs a layout pass; the model has not changed,
        # so a reset would be wrong (it would drop the selection).
        self.scheduleDelayedItemsLayout()
        self.viewport().update()

    # ---------------------------------------------------------------- data

    def set_rows(self, rows: list[dict], keep_selected_id: int | None = None) -> None:
        self._model.set_rows(rows)
        if keep_selected_id is not None:
            self._select_silently(keep_selected_id)

    def row_count(self) -> int:
        """Real message rows only, excluding synthetic date headers."""
        return sum(1 for r in self._model._rows if not r.get("is_header"))

    def selected_email_id(self) -> int | None:
        indexes = self.selectionModel().selectedIndexes()
        if not indexes:
            return None
        msg = indexes[0].data(ROLE_MSG)
        return msg.get("id") if msg else None

    def select_email(self, email_id: int) -> None:
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

    # ------------------------------------------------------ hover actions

    def _hit(self, pos: QPoint) -> tuple[int, str, dict | None]:
        index = self.indexAt(pos)
        if not index.isValid():
            return -1, "", None
        msg = index.data(ROLE_MSG)
        if not msg or msg.get("is_header"):
            return -1, "", None
        rect = self.visualRect(index).adjusted(t.SPACE_SM, 1, -t.SPACE_SM, -1)
        for name, box in self._delegate.action_rects(rect).items():
            if box.contains(pos):
                return index.row(), name, msg
        return index.row(), "", msg

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        row, action, _ = self._hit(event.position().toPoint())
        if row != self._delegate.hover_row or action != self._delegate.hover_action:
            self._delegate.hover_row = row
            self._delegate.hover_action = action
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if action
                else Qt.CursorShape.ArrowCursor
            )
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        if self._delegate.hover_row != -1:
            self._delegate.hover_row = -1
            self._delegate.hover_action = ""
            self.viewport().update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """A click on a quick action acts on that row WITHOUT selecting it.

        Starring the fourth message should not throw away the message you
        are reading, which is what letting the click fall through to the
        selection model would do.
        """
        row, action, msg = self._hit(event.position().toPoint())
        if action and msg:
            if action == ACTION_STAR:
                self.star_toggled.emit(msg["id"])
            else:
                self.delete_requested.emit(msg["id"])
            event.accept()
            return
        super().mousePressEvent(event)

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

    # ---------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802
        """Rows, then a softened boundary at whichever edge is scrolled.

        THE EDGE FADE IS THE POINT. A message list that ends in a hard
        horizontal cut against the toolbar reads as guillotined - the row
        at the boundary is visibly sliced, and nothing says the list
        continues. Softening those two edges is the single cheapest thing
        that makes a scrolling surface feel finished. Adapted from Magic
        UI's ProgressiveBlur; see primitives.paint_edge_fade for why the
        blur itself is not reproduced.

        Painted only where it means something: the top fade appears once
        there is content scrolled above, the bottom once there is content
        below. A list that fits entirely on screen has neither, because
        nothing is being cut off and a permanent vignette would just be
        decoration.
        """
        super().paintEvent(event)

        bar = self.verticalScrollBar()
        at_top = bar.value() <= bar.minimum()
        at_bottom = bar.value() >= bar.maximum()
        if at_top and at_bottom:
            return  # everything fits; nothing is being cut off

        painter = QPainter(self.viewport())
        paint_edge_fade(
            painter, self.viewport().rect(), t.BG_APP,
            top=not at_top, bottom=not at_bottom,
        )
        painter.end()

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        """Repaint the whole viewport while scrolling.

        QListView scrolls by blitting the unchanged region and repainting
        only the newly exposed strip, which is exactly right for rows and
        exactly wrong for a gradient pinned to the viewport edge: the
        blitted pixels carry the old fade with them and it smears down the
        list. Cheap to avoid - the viewport is a few hundred rows tall at
        most, and this is the one widget where correctness beats the blit.
        """
        super().scrollContentsBy(dx, dy)
        self.viewport().update()

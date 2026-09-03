"""Sidebar navigation: a row, and the indicator that travels between rows.

The selected state used to be drawn by each row for itself - a stylesheet
fill plus a bar that grew from zero height in place. That reads as two
separate things blinking, because it is: the old row's mark vanishes and
the new row's mark appears, and nothing connects them.

`NavList` fixes it with the *sliding indicator* pattern (transitions.dev
"tabs sliding"): one indicator, owned by the container, painted *behind*
the rows, that travels from the old row's geometry to the new one over
250ms on the smooth-out curve. Selection stops being a blink and becomes a
movement, which is also the honest description of what happened - you
moved, the mailbox did not.

It is symmetric on purpose: the same duration and curve in both
directions, because it is the same journey either way. Open/close
asymmetry belongs to things that enter and leave, not to something that
travels.

`NavPill` keeps the parts that genuinely belong to a row - its hover
surface, icon, label and count - and animates its hover rather than
snapping, because a stylesheet cannot.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from app.ui import theme as t
from app.ui.components.badge import CountBadge
from app.ui.design import motion
from app.ui.design.motion import StateAnimator, ValueAnimator, blend
from app.ui.svg_icon import tinted_pixmap

_BAR_WIDTH = 3
_BAR_HEIGHT_RATIO = 0.5
_ICON_GAP = t.SPACE_LG


class NavPill(QPushButton):
    """One navigation row. Paints its own hover; selection is drawn by the
    `NavList` behind it so it can travel."""

    def __init__(self, text: str = "", icon: str | None = None, parent=None):
        super().__init__(text, parent)
        self.setObjectName("navItem")
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(t.make_font("nav_label"))
        self.setMinimumHeight(t.TAB_HEIGHT + t.SPACE_SM)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setProperty("painted", "true")

        self._icon_name = icon
        self._collapsed = False
        self._label = text

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, t.SPACE_LG, 0)
        row.addStretch(1)
        self.badge = CountBadge("quiet")
        row.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._anim = StateAnimator(
            self, hover=motion.DURATION_HOVER, press=motion.DURATION_PRESS,
        )
        self.toggled.connect(lambda _on: self.update())

    # -------------------------------------------------------------- state

    def set_count(self, count: int) -> None:
        self.badge.set_count(count)
        self.badge.set_tone("accent" if self.isChecked() and count else "quiet")

    def set_collapsed(self, collapsed: bool) -> None:
        """Icon-rail mode: the label and count give up their space."""
        self._collapsed = collapsed
        self.badge.setVisible(not collapsed and bool(self.badge.text()))
        self.update()

    def refresh_icon(self) -> None:
        self.update()

    # ------------------------------------------------------------- events

    def enterEvent(self, event) -> None:  # noqa: N802
        self._anim.to("hover", 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._anim.to("hover", 0.0, exiting=True)
        self._anim.to("press", 0.0, exiting=True)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._anim.to("press", 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._anim.to("press", 0.0, exiting=True)
        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = t.theme_manager.palette
        rect = QRectF(self.rect())

        # Hover only. The selected surface is the NavList's travelling
        # indicator, painted underneath this widget.
        hover = max(self._anim["hover"], self._anim["press"] * 0.8)
        if hover > 0.01 and not self.isChecked():
            fill = blend(QColor(0, 0, 0, 0), QColor(palette.surface_hover), hover)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, t.RADIUS_MD, t.RADIUS_MD)

        checked = self.isChecked()
        text_color = QColor(palette.text_primary if checked else palette.text_secondary)
        if not checked and hover > 0.01:
            text_color = blend(palette.text_secondary, palette.text_primary, hover)

        x = t.SPACE_XL
        if self._icon_name:
            size = t.ICON_MD
            tint = QColor(palette.accent) if checked else text_color
            painter.drawPixmap(
                int(x), int(rect.center().y() - size / 2),
                tinted_pixmap(self._icon_name, size, tint.name()),
            )
            x += size + _ICON_GAP

        if not self._collapsed and self._label:
            font = t.make_font("nav_label_active" if checked else "nav_label")
            painter.setFont(font)
            painter.setPen(text_color)
            metrics = QFontMetrics(font)
            # sizeHint, not width(): a hidden widget is never laid out and
            # keeps Qt's default 640x480 geometry, which would elide every
            # label without a count down to an ellipsis.
            badge_width = (
                self.badge.sizeHint().width() + t.SPACE_MD
                if self.badge.isVisible() else 0
            )
            available = int(rect.width() - x - badge_width - t.SPACE_XL)
            painter.drawText(
                QRectF(x, rect.top(), max(10, available), rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                metrics.elidedText(self._label, Qt.TextElideMode.ElideRight,
                                   max(10, available)),
            )
        painter.end()

    def setText(self, text: str) -> None:  # noqa: N802
        # The label is painted, not laid out by Qt, so keep both in step.
        self._label = text
        super().setText(text)


NavItem = NavPill


class NavList(QWidget):
    """A column of `NavPill`s with one indicator that travels between them.

    The indicator carries both halves of the selected state - the tinted
    fill and the accent bar on the leading edge - so they move together as
    a single object.
    """

    selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[NavPill] = []
        self._current = -1
        self._collapsed = False

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(t.SPACE_2XS)
        self._column = column

        # Position and height of the indicator, in this widget's
        # coordinates. Animating the values rather than moving a child
        # widget keeps it behind the rows without any stacking games.
        self._y = ValueAnimator(self, 0.0, motion.TABS_DURATION,
                                motion.EASE_SMOOTH_OUT)
        self._height = ValueAnimator(self, 0.0, motion.TABS_DURATION,
                                     motion.EASE_SMOOTH_OUT)
        self._presence = ValueAnimator(self, 0.0, motion.DURATION_FAST,
                                       motion.EASE_SMOOTH_OUT)
        # Whether the indicator has ever been positioned. The first
        # placement lands, later ones travel - gating on the fade-in
        # progress instead would make a fast second click jump.
        self._placed = False

    # --------------------------------------------------------------- api

    def add_item(self, item: NavPill) -> None:
        index = len(self._items)
        self._items.append(item)
        self._column.addWidget(item)
        item.clicked.connect(lambda _=False, i=index: self.set_current(i))

    def items(self) -> list[NavPill]:
        return list(self._items)

    def current(self) -> int:
        return self._current

    def set_current(self, index: int, *, animate: bool = True,
                    emit: bool = True) -> None:
        if not (0 <= index < len(self._items)):
            self.clear_current()
            return
        previous = self._current
        self._current = index
        for i, item in enumerate(self._items):
            item.setChecked(i == index)
            item.set_count(item.badge.count)
        self._move_to(index, animate=animate and previous >= 0)
        if emit and previous != index:
            self.selected.emit(index)

    def clear_current(self) -> None:
        self._current = -1
        for item in self._items:
            item.setChecked(False)
        self._presence.to(0.0, duration=motion.DURATION_QUICK)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        for item in self._items:
            item.set_collapsed(collapsed)

    # ------------------------------------------------------------ layout

    def _move_to(self, index: int, *, animate: bool) -> None:
        item = self._items[index]
        top = float(item.y())
        height = float(item.height())
        if animate and self._placed:
            self._y.to(top)
            self._height.to(height)
        else:
            self._y.set_now(top)
            self._height.set_now(height)
        self._placed = True
        self._presence.to(1.0, duration=motion.DURATION_FAST)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # On a resize the indicator snaps rather than tweening: it has not
        # travelled anywhere, the layout moved under it.
        if 0 <= self._current < len(self._items):
            item = self._items[self._current]
            self._y.set_now(float(item.y()))
            self._height.set_now(float(item.height()))

    # ------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802
        presence = self._presence.value
        if presence <= 0.01 or self._height.value <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = t.theme_manager.palette

        rect = QRectF(0, self._y.value, self.width(), self._height.value)
        fill = QColor(palette.selected)
        fill.setAlphaF(presence)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, t.RADIUS_MD, t.RADIUS_MD)

        bar_height = rect.height() * _BAR_HEIGHT_RATIO
        bar = QColor(palette.accent)
        bar.setAlphaF(presence)
        painter.setBrush(bar)
        painter.drawRoundedRect(
            QRectF(rect.left(), rect.top() + (rect.height() - bar_height) / 2,
                   _BAR_WIDTH, bar_height),
            _BAR_WIDTH / 2, _BAR_WIDTH / 2,
        )
        painter.end()

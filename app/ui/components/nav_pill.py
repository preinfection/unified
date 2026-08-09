"""Sidebar navigation item with the reference's signature selected-state
indicator: a 3px accent bar on the row's left edge that grows from zero
height when the item becomes active and shrinks back when it doesn't.

QSS can express the fill and text color of a checked button but not an
animated sub-element, so the bar is painted here over the styled button.
The reference sizes it at ~53% of the row height, centered vertically,
with a 2px corner radius, and tweens it over T_NORMAL - all reproduced
below against Unified's equivalent tokens.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
)
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QPushButton

from app.ui import theme as t

_BAR_WIDTH = 3
_BAR_HEIGHT_RATIO = 0.53   # reference: indH = clamp(btnH * 0.53, 8, btnH)


class NavPill(QPushButton):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("navPill")
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._indicator = 1.0 if self.isChecked() else 0.0
        self._anim = QPropertyAnimation(self, b"indicator", self)
        self._anim.setDuration(t.DURATION_BASE)
        # The reference eases every transition with Quint/Out.
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuint)
        self.toggled.connect(self._animate_to)

    def _animate_to(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._indicator)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _get_indicator(self) -> float:
        return self._indicator

    def _set_indicator(self, value: float) -> None:
        self._indicator = value
        self.update()

    indicator = Property(float, _get_indicator, _set_indicator)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._indicator <= 0.001:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(t.qcolor(t.ACCENT))
        full = self.height() * _BAR_HEIGHT_RATIO
        height = full * self._indicator
        painter.drawRoundedRect(
            QRectF(0.0, (self.height() - height) / 2.0, float(_BAR_WIDTH), height),
            2.0, 2.0,
        )
        painter.end()

"""AccentButton: a primary-action button with a real animated press-dip,
translating the reference's button micro-interaction (a quick darken on
press, releasing back on mouseup) instead of QSS's instant, un-tweened
:pressed color swap.

Painting strategy: this subclass draws its own animated gradient
background in paintEvent, then calls the base QPushButton paintEvent so
Qt's normal style engine still lays out and draws the icon/text/focus
rect - only the background is custom, so this stays a real QPushButton
(clickable, focusable, works with QDialogButtonBox-adjacent layouts)
rather than a bespoke widget that has to reimplement all of that.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QPushButton

from app.ui import theme as t


def _mix(color_a: str, color_b: str, fraction: float) -> QColor:
    a, b = QColor(color_a), QColor(color_b)
    fraction = max(0.0, min(1.0, fraction))
    return QColor(
        round(a.red() + (b.red() - a.red()) * fraction),
        round(a.green() + (b.green() - a.green()) * fraction),
        round(a.blue() + (b.blue() - a.blue()) * fraction),
    )


class AccentButton(QPushButton):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("accentButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(t.make_font("button"))
        self.setMinimumHeight(t.HEIGHT_MD)

        self._press = 0.0   # 0 = resting, 1 = fully pressed
        self._hover = 0.0   # 0 = idle, 1 = hovered
        self._press_anim = QPropertyAnimation(self, b"pressProgress", self)
        self._press_anim.setDuration(t.DURATION_FAST)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(t.DURATION_FAST)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # -- animated properties ------------------------------------------------

    def _get_press(self) -> float:
        return self._press

    def _set_press(self, value: float) -> None:
        self._press = value
        self.update()

    pressProgress = Property(float, _get_press, _set_press)

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hoverProgress = Property(float, _get_hover, _set_hover)

    def _animate_press(self, end: float) -> None:
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press)
        self._press_anim.setEndValue(end)
        self._press_anim.start()

    def _animate_hover(self, end: float) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(end)
        self._hover_anim.start()

    # -- events ---------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled():
            self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled():
            self._animate_press(1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._animate_press(0.0)
        super().mouseReleaseEvent(event)

    # -- paint ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        if self.isEnabled():
            top = _mix(t.ACCENT_HOVER, t.ACCENT_GLOW, self._hover * 0.5)
            bottom = _mix(t.ACCENT, t.ACCENT_HOVER, self._hover * 0.5)
            top = _mix(top.name(), t.ACCENT_PRESSED, self._press)
            bottom = _mix(bottom.name(), t.ACCENT_PRESSED, self._press)
            border = QColor(t.ACCENT)
        else:
            top = bottom = QColor(t.BG_SELECTED)
            border = QColor(t.BORDER)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, bottom)
        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(rect, t.RADIUS_SM, t.RADIUS_SM)
        painter.end()

        super().paintEvent(event)

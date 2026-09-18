"""Sidebar navigation item.

WHAT THIS USED TO DO, AND WHY IT STOPPED

It painted a 3px accent bar down the row's left edge, grown from zero
height on selection, on top of a QSS rule that ALSO gave the checked state
an accent-tinted fill, an accent text color and a heavier weight. Four
simultaneous cues for one boolean.

Two problems, and the second is the real one:

  * A colored bar on the left edge of a row is decoration standing in for
    meaning. It is the cheapest way to make a list item look designed, it
    is everywhere, and it is never the clearest available answer.
  * Stacking four cues does not make a state clearer, it makes the sidebar
    louder. A user cannot tell which of the four is the signal, so all four
    become noise, and the accent - the app's single brightest value - gets
    spent on "which folder am I in", which the user already knows.

So the row is now a SURFACE. Selected means the item sits on the raised
warm step (BG_SELECTED) with primary text; unselected is transparent with
secondary text. One cue, matching the message-list rows exactly, so a
glance at any part of the app reads "selected" the same way.

The animation survives, and it is better than what it replaced: instead of
growing a bar, it fades the surface in over T_NORMAL. Motion is attached to
a state change rather than to an ornament, and the fill is painted here
rather than in QSS because Qt Style Sheets cannot animate a background.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QPropertyAnimation,
    QRectF,
    Qt,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QPushButton

from app.ui import motion, theme as t

# How much of the selected surface a mere hover is worth. Hover has to be
# clearly less than selected or the two states argue with each other.
_HOVER_STRENGTH = 0.55


class NavPill(QPushButton):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("navPill")
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._indicator = 1.0 if self.isChecked() else 0.0
        self._hovered = False
        self._anim = QPropertyAnimation(self, b"indicator", self)
        self._anim.setDuration(t.DURATION_BASE)
        # Via motion.curve() rather than naming OutQuint here: the same
        # value, but stated in one place, so changing the app's curve
        # does not leave one component behind.
        self._anim.setEasingCurve(motion.curve())
        self.toggled.connect(self._animate_to)

    def _animate_to(self, checked: bool) -> None:
        end = 1.0 if checked else 0.0
        self._anim.stop()
        if not motion.motion_enabled():
            self._set_indicator(end)
            return
        self._anim.setStartValue(self._indicator)
        self._anim.setEndValue(end)
        self._anim.start()

    def _get_indicator(self) -> float:
        return self._indicator

    def _set_indicator(self, value: float) -> None:
        self._indicator = value
        self.update()

    indicator = Property(float, _get_indicator, _set_indicator)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        """The surface is painted BEFORE the button's own label.

        QPushButton.paintEvent draws the text; anything painted after it
        would cover the label. The old implementation could get away with
        painting afterwards because a 3px bar at the very edge never
        overlapped the text - a full-bleed fill does.
        """
        strength = self._indicator
        if self._hovered and not self.isChecked():
            strength = max(strength, _HOVER_STRENGTH)

        if strength > 0.001:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            fill = QColor(t.BG_SELECTED)
            fill.setAlphaF(min(1.0, strength))
            painter.setBrush(fill)
            painter.drawRoundedRect(
                QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                float(t.RADIUS_MD), float(t.RADIUS_MD),
            )
            painter.end()

        super().paintEvent(event)

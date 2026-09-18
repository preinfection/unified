"""A sliding pill toggle switch, used in place of a checkbox for on/off
settings - QSS can style a QCheckBox's indicator box, but it cannot
animate a knob sliding across a track, so this paints and animates
itself instead.
"""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QRectF, Qt, Property
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCheckBox

from app.ui import motion, theme as t

_WIDTH = 38
_HEIGHT = 22
_KNOB_MARGIN = 3
_KNOB_SIZE = _HEIGHT - 2 * _KNOB_MARGIN


class Toggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(_WIDTH, _HEIGHT)
        self._knob_pos = 1.0 if self.isChecked() else 0.0

        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(t.DURATION_BASE)
        # THE APP'S CURVE, not this component's own. It was OutCubic
        # while the nav pill, the sidebar and every motion.py helper
        # were OutQuint - so a toggle settled visibly differently from
        # everything else on the same screen, which is the kind of
        # difference nobody can name and everybody feels.
        self._anim.setEasingCurve(motion.curve())
        self.toggled.connect(self._animate_to)

    def _animate_to(self, checked: bool) -> None:
        end = 1.0 if checked else 0.0
        self._anim.stop()
        # Reduced motion has to reach the knob too: a switch that still
        # slides when every other transition has been turned off is the
        # one thing the setting was asked to stop.
        if not motion.motion_enabled():
            self._set_knob_pos(end)
            return
        self._anim.setStartValue(self._knob_pos)
        self._anim.setEndValue(end)
        self._anim.start()

    def _get_knob_pos(self) -> float:
        return self._knob_pos

    def _set_knob_pos(self, value: float) -> None:
        self._knob_pos = value
        self.update()

    knobPos = Property(float, _get_knob_pos, _set_knob_pos)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        off_color, on_color = QColor(t.BORDER_LIGHT), QColor(t.ACCENT)
        track = QColor(
            round(off_color.red() + (on_color.red() - off_color.red()) * self._knob_pos),
            round(off_color.green() + (on_color.green() - off_color.green()) * self._knob_pos),
            round(off_color.blue() + (on_color.blue() - off_color.blue()) * self._knob_pos),
        )
        if not self.isEnabled():
            track = QColor(t.BORDER)
        painter.setBrush(track)
        painter.drawRoundedRect(self.rect(), _HEIGHT / 2, _HEIGHT / 2)

        knob_x = _KNOB_MARGIN + self._knob_pos * (_WIDTH - _KNOB_SIZE - 2 * _KNOB_MARGIN)
        painter.setBrush(QColor(t.TEXT_ON_ACCENT))
        painter.drawEllipse(QRectF(knob_x, _KNOB_MARGIN, _KNOB_SIZE, _KNOB_SIZE))

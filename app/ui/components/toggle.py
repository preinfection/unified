"""A sliding pill toggle switch, used in place of a checkbox for on/off
settings - QSS can style a QCheckBox's indicator box, but it cannot
animate a knob sliding across a track, so this paints and animates
itself instead.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, Property
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCheckBox

from app.ui import theme as t
from app.ui.design import motion

_WIDTH = 38
_HEIGHT = 22
_KNOB_MARGIN = 3
_KNOB_SIZE = _HEIGHT - 2 * _KNOB_MARGIN


class Toggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(_WIDTH, _HEIGHT)
        # Tells the stylesheet not to draw a checkbox indicator over the
        # track this widget paints for itself.
        self.setProperty("role", "switch")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._knob_pos = 1.0 if self.isChecked() else 0.0

        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setEasingCurve(motion.EASE_TOGGLE)
        self.toggled.connect(self._animate_to)

    def _animate_to(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        duration = t.duration(motion.TOGGLE_TRAVEL)
        if not duration:
            # Reduced motion: the state still changes, it just does not
            # travel. Asking the theme manager here means the preference
            # is honored in one place rather than re-checked per widget.
            self._anim.stop()
            self._set_knob_pos(target)
            return
        self._anim.stop()
        self._anim.setDuration(duration)
        self._anim.setStartValue(self._knob_pos)
        self._anim.setEndValue(target)
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

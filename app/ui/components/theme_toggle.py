"""The theme control: a sun and a moon, and a surface that sits under the
one that is current.

ADAPTED FROM MAGIC UI'S ANIMATED THEME TOGGLER. What that component gets
right is not the icon - it is that the NEW THEME SPREADS OUT FROM THE
CONTROL. A circle opens at the button and the whole page changes inside
it, so the eye can see what caused the change and where it came from.
That reveal is kept, natively: see motion.reveal_theme_change, which
MainWindow runs when this control asks for a new mode.

What changed for a settings row, and why:

  * BOTH STATES ARE VISIBLE. The web toggler is a single icon that swaps
    sun for moon, which leaves the reader to work out whether the icon
    shows the current theme or the one it will switch to - a genuinely
    ambiguous control. Here the sun and the moon both sit in the track
    and the selected surface rests under the current one, so the state is
    read, not inferred. It is the same "one surface that slides" the dock
    uses for the current folder, so the product has one way of saying
    "this one".
  * NO DROPDOWN. Two options do not need a menu; the dropdown this
    replaces took two clicks and a read to do what one click does now.
  * REDUCED MOTION: the surface is simply where it belongs, and the
    window changes theme in one frame.

Keyboard: it is a checkable button (checked = dark), so Space toggles;
Left and Right choose light and dark directly, the way a two-segment
control is expected to behave.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEvent, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton

from app.ui import motion, theme as t
from app.ui.svg_icon import paint_icon

_SEGMENT = 34
_INSET = 2
_GLYPH = 16
WIDTH = 2 * _SEGMENT + 2 * _INSET
HEIGHT = t.HEIGHT_MD


class ThemeToggle(QAbstractButton):
    """checked == dark. Emits mode_requested("light" | "dark")."""

    mode_requested = Signal(str)

    def __init__(self, mode: str = "dark", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(mode == "dark")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._pos = 1.0 if self.isChecked() else 0.0
        self._keyboard_focus = False
        self._hovered = False

        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(t.DURATION_BASE)
        self._anim.setEasingCurve(motion.curve())
        self.toggled.connect(self._on_toggled)
        self._describe()

    # ------------------------------------------------------------- state

    def mode(self) -> str:
        return "dark" if self.isChecked() else "light"

    def set_mode(self, mode: str) -> None:
        """Show a mode without asking for it (e.g. a revert on Cancel)."""
        self.blockSignals(True)
        self.setChecked(mode == "dark")
        self.blockSignals(False)
        self._anim.stop()
        self._set_knob(1.0 if self.isChecked() else 0.0)
        self._describe()

    def _on_toggled(self, checked: bool) -> None:
        self._describe()
        end = 1.0 if checked else 0.0
        self._anim.stop()
        if not motion.motion_enabled():
            self._set_knob(end)
        else:
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(end)
            self._anim.start()
        self.mode_requested.emit(self.mode())

    def _describe(self) -> None:
        current = "Dark" if self.isChecked() else "Light"
        other = "light" if self.isChecked() else "dark"
        self.setAccessibleName("Theme")
        self.setAccessibleDescription(f"{current} theme. Press to switch to {other}.")
        self.setToolTip(f"{current} theme - click for {other}")

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = float(value)
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    # ----------------------------------------------------------- keyboard

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Left and self.isChecked():
            self.setChecked(False)
            return
        if key == Qt.Key.Key_Right and not self.isChecked():
            self.setChecked(True)
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._keyboard_focus = event.reason() in (
            Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._keyboard_focus = False
        self.update()
        super().focusOutEvent(event)

    def event(self, event) -> bool:
        if event.type() in (QEvent.Type.HoverEnter, QEvent.Type.HoverLeave):
            self._hovered = event.type() == QEvent.Type.HoverEnter
            self.update()
        return super().event(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(WIDTH, HEIGHT)

    # --------------------------------------------------------------- geometry

    def segment_rect(self, index: int) -> QRectF:
        """0 = light (sun), 1 = dark (moon)."""
        return QRectF(_INSET + index * _SEGMENT, _INSET,
                      _SEGMENT, HEIGHT - 2 * _INSET)

    def knob_rect(self) -> QRectF:
        light, dark = self.segment_rect(0), self.segment_rect(1)
        x = light.left() + (dark.left() - light.left()) * self._pos
        return QRectF(x, light.top(), light.width(), light.height())

    # ------------------------------------------------------------------ paint

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        track = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # The track is an input's surface and edge, so it sits in a
        # settings row like every other control there.
        border = t.BORDER_LIGHT if (self._hovered and self.isEnabled()) else t.BORDER
        if self._keyboard_focus and self.hasFocus():
            border = t.FOCUS_RING
        painter.setPen(QPen(QColor(border), 1.0))
        painter.setBrush(QColor(t.BG_PANEL))
        painter.drawRoundedRect(track, float(t.RADIUS_MD), float(t.RADIUS_MD))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.BG_SELECTED))
        painter.drawRoundedRect(self.knob_rect(), float(t.RADIUS_SM), float(t.RADIUS_SM))

        # Each glyph brightens as the surface arrives under it, so the
        # icon and the surface agree at every frame rather than the colour
        # snapping at the end of the slide.
        for index, name in ((0, "sun"), (1, "moon")):
            weight = self._pos if index == 1 else 1.0 - self._pos
            colour = t.mix(t.ICON_SECONDARY, t.ICON_SELECTED, weight)
            if not self.isEnabled():
                colour = t.ICON_DISABLED
            seg = self.segment_rect(index)
            glyph = QRectF(seg.center().x() - _GLYPH / 2, seg.center().y() - _GLYPH / 2,
                           _GLYPH, _GLYPH)
            paint_icon(painter, name, glyph, colour)
        painter.end()

    def retheme(self) -> None:
        self.update()

"""An optional smoothed pointer. Off by default, and deliberately narrow.

ADAPTED FROM MAGIC UI'S SMOOTH CURSOR, which hides the system pointer
and draws its own arrow that follows the mouse through a spring, so the
pointer glides instead of jumping. On a marketing page that is a flourish
you look at for ten seconds.

IN A MAIL CLIENT IT IS A TRADE, and it is stated honestly here rather
than hidden: a follower that is smoothed is, by definition, BEHIND the
real pointer. With Magic UI's own spring (stiffness 400, damping 45) the
drawn arrow trails a moving pointer by about 110ms and takes nearly half
a second to settle after a 200px flick. A click lands where the real,
hidden pointer is, not where the arrow is drawn - so for anyone moving
fast and clicking immediately, the effect costs precision. That is why:

  * IT IS OFF UNLESS SOMEONE TURNS IT ON (Settings > Appearance, marked
    experimental), and the setting says what it costs.
  * THE SPRING IS STIFFER than the web original and critically damped:
    it trails a moving pointer by about 54ms instead of 110, and settles
    after a 200px flick in about 205ms instead of 480 (both measured by
    tracking_lag_ms / settle_time_ms below). Less glide, half the lag.
  * IT STEPS ASIDE WHEREVER PRECISION MATTERS. The native pointer is used
    over text (the I-beam), over splitter and resize handles, while any
    mouse button is held (drags, selections, the press itself - the
    follower snaps to the real position on press so the click is seen
    where it lands), outside Unified's own windows, and whenever motion
    is reduced.
  * ONE OVERLAY FOR THE WHOLE APPLICATION - a single small, input-
    transparent window - and one timer that runs only while the arrow is
    still catching up. Per-widget followers would multiply both.

The pointer is Unified's own arrow, not a copy of any system's, drawn
dark with a light edge so it reads on both themes.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QEvent, QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen, QWindow
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from app.ui import motion

# Stiffer than Magic UI's (400 / 45 / 1) - see the module docstring.
STIFFNESS = 1400.0
DAMPING = 75.0
MASS = 1.0
FRAME_MS = 16
SIZE = 28                     # overlay box; the arrow is ~18px tall in it
HOTSPOT = QPointF(5.0, 4.0)   # the arrow's tip inside the box

_FOLLOW_SHAPES = (Qt.CursorShape.ArrowCursor, Qt.CursorShape.PointingHandCursor)
_TEXT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)


def arrow_path() -> QPainterPath:
    """A plain pointer arrow with a softened tip, tip at HOTSPOT."""
    x, y = HOTSPOT.x(), HOTSPOT.y()
    path = QPainterPath()
    path.moveTo(x, y)
    path.lineTo(x, y + 16.0)
    path.lineTo(x + 4.2, y + 12.3)
    path.lineTo(x + 7.0, y + 18.2)
    path.lineTo(x + 9.6, y + 17.0)
    path.lineTo(x + 6.9, y + 11.2)
    path.lineTo(x + 12.2, y + 11.2)
    path.closeSubpath()
    return path


class _PointerOverlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("smoothPointer")
        self.setFixedSize(SIZE, SIZE)
        self._path = arrow_path()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # A soft offset shadow gives it the lift a system pointer has.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawPath(self._path.translated(0.8, 1.2))
        painter.setBrush(QColor(20, 17, 14))
        painter.setPen(QPen(QColor(251, 250, 247), 1.4))
        painter.drawPath(self._path)
        painter.end()


class SmoothPointer(QObject):
    """Install once per application; enable or disable at any time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._following = False
        self._overridden = False
        self._overlay: _PointerOverlay | None = None
        self._pos = QPointF()
        self._vel = QPointF()
        self._target = QPointF()
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ---------------------------------------------------------------- state

    def is_enabled(self) -> bool:
        return self._enabled

    def is_following(self) -> bool:
        return self._following

    def position(self) -> QPointF:
        return QPointF(self._pos)

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._enabled:
            return
        self._enabled = enabled
        app = QApplication.instance()
        if enabled:
            app.installEventFilter(self)
        else:
            app.removeEventFilter(self)
            self._to_native()

    # ------------------------------------------------------------ decisions

    @staticmethod
    def wants_native(widget: QWidget | None, buttons) -> bool:
        """True where the real pointer must be shown."""
        if not motion.motion_enabled():
            return True
        if buttons != Qt.MouseButton.NoButton:
            return True
        if widget is None:
            return True
        probe = widget
        while probe is not None:
            if isinstance(probe, _TEXT_TYPES):
                return True
            probe = probe.parentWidget()
        return widget.cursor().shape() not in _FOLLOW_SHAPES

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QEvent.Type.MouseMove and isinstance(obj, QWindow):
            self._on_move(event.globalPosition(), event.buttons())
        elif kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick) \
                and isinstance(obj, QWindow):
            # The press is where precision is owed: the real pointer, now.
            self._to_native()
        elif kind == QEvent.Type.Leave and isinstance(obj, QWindow):
            self._to_native()
        elif kind == QEvent.Type.ApplicationDeactivate:
            self._to_native()
        return False

    def _on_move(self, global_pos: QPointF, buttons) -> None:
        widget = QApplication.widgetAt(global_pos.toPoint())
        if widget is not None and isinstance(widget, _PointerOverlay):
            widget = None
        if self.wants_native(widget, buttons):
            self._to_native()
            return
        self._target = QPointF(global_pos)
        if not self._following:
            self._start_following()
        if not self._timer.isActive():
            self._clock.start()
            self._timer.start()

    # ------------------------------------------------------------- follow

    def _start_following(self) -> None:
        self._following = True
        # Start where the pointer IS, so switching on never makes the arrow
        # fly in from wherever it was last seen.
        self._pos = QPointF(self._target)
        self._vel = QPointF()
        if self._overlay is None:
            self._overlay = _PointerOverlay()
        self._place()
        self._overlay.show()
        if not self._overridden:
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.BlankCursor))
            self._overridden = True

    def _to_native(self) -> None:
        self._timer.stop()
        if self._overridden:
            QApplication.restoreOverrideCursor()
            self._overridden = False
        if self._overlay is not None:
            self._overlay.hide()
        self._following = False

    def _place(self) -> None:
        if self._overlay is None:
            return
        top_left = self._pos - HOTSPOT
        self._overlay.move(int(round(top_left.x())), int(round(top_left.y())))

    def _tick(self) -> None:
        elapsed = self._clock.restart() / 1000.0 if self._clock.isValid() else 0.016
        elapsed = min(max(elapsed, 0.001), 0.05)
        steps = max(1, int(math.ceil(elapsed / 0.004)))
        dt = elapsed / steps
        pos, vel, target = self._pos, self._vel, self._target
        for _ in range(steps):
            accel = ((target - pos) * STIFFNESS - vel * DAMPING) / MASS
            vel = vel + accel * dt
            pos = pos + vel * dt
        self._pos, self._vel = pos, vel
        self._place()
        offset = target - pos
        if math.hypot(offset.x(), offset.y()) < 0.3 and math.hypot(vel.x(), vel.y()) < 5:
            self._pos, self._vel = QPointF(target), QPointF()
            self._place()
            self._timer.stop()

    # ------------------------------------------------------------- measure

    @staticmethod
    def tracking_lag_ms() -> float:
        """How far behind a pointer moving at constant speed the arrow
        runs, in time: damping / stiffness for this spring."""
        return DAMPING / STIFFNESS * 1000.0

    @staticmethod
    def settle_time_ms(distance: float = 200.0, within: float = 1.0) -> float:
        """How long the arrow takes to come within `within` px of a pointer
        that jumped `distance` px - the lag this effect costs, measured by
        the same integrator the timer runs."""
        pos, vel, target, t_ms = 0.0, 0.0, distance, 0.0
        dt = 0.001
        while abs(target - pos) > within and t_ms < 5000:
            accel = ((target - pos) * STIFFNESS - vel * DAMPING) / MASS
            vel += accel * dt
            pos += vel * dt
            t_ms += 1.0
        return t_ms

    def shutdown(self) -> None:
        self.set_enabled(False)
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None

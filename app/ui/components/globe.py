"""A dotted globe for the opening surface.

ADAPTED FROM MAGIC UI'S GLOBE (itself the "cobe" WebGL globe): a sphere
drawn as points, the far side dimmer than the near, turning slowly. What
reads there is not the map - it is DEPTH FROM DOTS: points that brighten
as they come round to face you and fade as they go over the edge give a
sphere without a single line being drawn.

What changed for a mail client's first second on screen:

  * NO WEBGL AND NO MAP. A few hundred points on a dotted graticule - the
    parallels and meridians every globe icon uses - painted with QPainter.
    Without land data the graticule is what makes it read as a globe
    rather than a ball; it is also far sparser, which is the point.
  * QUIET. The dots are the tertiary ink, not the accent, there is no
    glow and no markers, and it is small. PRODUCT.md is explicit that
    nothing here should look like it is powering on; this is a mark in
    motion, not a light show.
  * SLOW, AND IT NEVER HOLDS ANYTHING UP. One revolution takes forty
    seconds, so a UI-thread stall while the mailbox opens moves it a
    fraction of a degree rather than making it visibly stutter - and the
    opening surface leaves the moment the app is ready, whatever the
    globe is doing.
  * ONE TIMER, ONLY WHILE VISIBLE, at 30 frames a second: at this speed a
    frame moves a dot a fraction of a pixel, and 60 would double the cost
    for nothing anyone could see.
  * REDUCED MOTION: a still globe, turned to a good angle. The final state
    is the drawing, not an empty space where an animation was.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from app.ui import motion, theme as t

DIAMETER = 104
SECONDS_PER_TURN = 40.0
FRAME_MS = 33
TILT = math.radians(18)          # the axis leans toward the viewer
_REST_ANGLE = math.radians(35)   # the still frame under reduced motion

PARALLELS = (-60, -40, -20, 0, 20, 40, 60)
MERIDIANS = 12
DOT_SPACING_DEG = 7.5


def graticule_points() -> list[tuple[float, float, float]]:
    """Unit-sphere points along the parallels and meridians, as (x, y, z)
    with y up. Built once; rotation is applied at paint time."""
    points: list[tuple[float, float, float]] = []

    def add(lat_deg: float, lon_deg: float) -> None:
        lat, lon = math.radians(lat_deg), math.radians(lon_deg)
        points.append((math.cos(lat) * math.sin(lon), math.sin(lat),
                       math.cos(lat) * math.cos(lon)))

    for lat in PARALLELS:
        # Fewer dots on the short rings near the poles, so the spacing
        # along every ring is about the same on screen.
        count = max(8, int(round(360 / DOT_SPACING_DEG * math.cos(math.radians(lat)))))
        for i in range(count):
            add(lat, 360.0 * i / count)
    for m in range(MERIDIANS):
        lon = 360.0 * m / MERIDIANS
        lat = -80.0
        while lat <= 80.0 + 1e-6:
            # Skip where a meridian crosses a parallel: that dot exists.
            if not any(abs(lat - p) < 1e-6 for p in PARALLELS):
                add(lat, lon)
            lat += DOT_SPACING_DEG
    return points


class DottedGlobe(QWidget):
    def __init__(self, diameter: int = DIAMETER, parent=None):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName("")      # decoration: nothing to announce
        self._points = graticule_points()
        self._angle = _REST_ANGLE
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.size()

    # ---------------------------------------------------------------- motion

    def is_turning(self) -> bool:
        return self._timer.isActive()

    def angle(self) -> float:
        return self._angle

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if motion.motion_enabled():
            self._clock.start()
            self._start_angle = self._angle
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        # Time-based, not frame-counted: a stalled frame catches up rather
        # than slowing the globe down.
        seconds = self._clock.elapsed() / 1000.0
        self._angle = self._start_angle + 2 * math.pi * seconds / SECONDS_PER_TURN
        self.update()

    # ----------------------------------------------------------------- paint

    def projected(self):
        """(x, y, depth) per point in widget coordinates, depth in -1..1
        (1 = facing the viewer)."""
        r = self.width() / 2.0 - 1.5
        cx, cy = self.width() / 2.0, self.height() / 2.0
        ca, sa = math.cos(self._angle), math.sin(self._angle)
        ct, st = math.cos(TILT), math.sin(TILT)
        out = []
        for x, y, z in self._points:
            # Spin about the vertical axis, then tilt toward the viewer.
            x1 = x * ca + z * sa
            z1 = -x * sa + z * ca
            y2 = y * ct - z1 * st
            z2 = y * st + z1 * ct
            out.append((cx + x1 * r, cy - y2 * r, z2))
        return out

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        base = QColor(t.TEXT_TERTIARY)
        points = sorted(self.projected(), key=lambda p: p[2])   # far first
        for x, y, depth in points:
            if depth < 0:
                # The far side: a whisper, so the sphere has a back.
                alpha = 0.10 + 0.08 * (1 + depth)
                size = 1.1
            else:
                # Near side: brighter and a touch larger toward the centre.
                alpha = 0.28 + 0.57 * depth
                size = 1.3 + 0.7 * depth
            colour = QColor(base)
            colour.setAlphaF(min(1.0, alpha))
            painter.setBrush(colour)
            painter.drawEllipse(QPointF(x, y), size, size)
        painter.end()

    def retheme(self) -> None:
        self.update()

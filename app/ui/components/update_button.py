"""The "Update" button: present only when a newer Unified exists.

ADAPTED FROM MAGIC UI'S SHINY BUTTON. That component runs a band of light
across its label forever - a gradient mask sliding from one edge to the
other, repeating every second or so. The idea worth keeping is that the
light MOVES ACROSS the button: it says "this is new" without a badge, a
colour, or a modal.

The loop is not kept. PRODUCT.md: nothing pulses, glows or moves without a
reason a user could name. So the band crosses exactly when there is a
reason:

  * ONCE WHEN THE BUTTON APPEARS - an update has just been found, which is
    the one moment the app has news;
  * ONCE WHEN THE POINTER ARRIVES - acknowledging it, like any hover.

Between those it is a quiet bordered button with the word Update, the
same material as the other toolbar controls, and it is the only
toolbar item that is text rather than an icon because it is the only one
that appears and disappears. Under reduced motion the band never runs.

Clicking opens the release page in the browser. Nothing is downloaded or
installed from inside the app - the user reads what changed and decides.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QPropertyAnimation, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QPushButton

from app.services.updates import Release, is_release_page
from app.ui import motion, theme as t

SHINE_MS = 900


class UpdateButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__("Update", parent)
        self.setObjectName("updateButton")
        self.setFont(t.make_font("button"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(t.HEIGHT_MD)
        self.setVisible(False)
        self._release: Release | None = None
        self._shine = -1.0          # band position: -1 = not running
        self._anim = QPropertyAnimation(self, b"shine", self)
        self._anim.setDuration(SHINE_MS)
        self._anim.setEasingCurve(motion.curve())
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.finished.connect(lambda: self._set_shine(-1.0))
        self.clicked.connect(self.open_release)

    # ------------------------------------------------------------- state

    def set_release(self, release: Release | None) -> bool:
        """Show the button for a newer release, or remove it entirely.

        Returns True when the button became visible, so the toolbar knows to
        lay itself out again. An absent button leaves no gap: it is hidden,
        and hidden widgets are skipped by the toolbar layout.
        """
        was_visible = not self.isHidden()
        self._release = release if release and is_release_page(release.url) else None
        if self._release is None:
            self.setVisible(False)
            return was_visible
        self.setToolTip(
            f"Unified {self._release.version} is available. "
            "Opens its release page in your browser."
        )
        self.setAccessibleName(f"Update available: Unified {self._release.version}")
        self.setVisible(True)
        if not was_visible:
            self.play_shine()
        return not was_visible

    def release(self) -> Release | None:
        return self._release

    def open_release(self) -> None:
        if self._release is not None and is_release_page(self._release.url):
            QDesktopServices.openUrl(QUrl(self._release.url))

    # ------------------------------------------------------------- shine

    def _get_shine(self) -> float:
        return self._shine

    def _set_shine(self, value: float) -> None:
        self._shine = float(value)
        self.update()

    shine = Property(float, _get_shine, _set_shine)

    def play_shine(self) -> bool:
        """One pass of light, if motion is on. Never loops."""
        if not motion.motion_enabled():
            return False
        self._anim.stop()
        self._anim.start()
        return True

    def is_shining(self) -> bool:
        return self._anim.state() == QPropertyAnimation.State.Running

    def enterEvent(self, event) -> None:  # noqa: N802
        if not self.is_shining():
            self.play_shine()
        super().enterEvent(event)

    # ------------------------------------------------------------- paint

    def sizeHint(self) -> QSize:  # noqa: N802
        text = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(text + 2 * t.SPACE_LG, t.HEIGHT_MD)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = float(t.RADIUS_SM)
        shape = QPainterPath()
        shape.addRoundedRect(rect, radius, radius)

        fill = QColor(t.BG_PANEL)
        if self.isDown():
            fill = QColor(t.mix(t.BG_PANEL, t.BG_SELECTED, 0.8))
        elif self.underMouse():
            fill = QColor(t.BG_HOVER)
        painter.fillPath(shape, fill)

        # The band: a soft diagonal glint crossing from left to right, on
        # the surface and along the edge. ALWAYS LIGHTER THAN THE SURFACE:
        # in the dark theme the ink is light, but in the light theme it is
        # near-black, and a dark band sweeping a pale button reads as a
        # smear, not a glint - so the light theme uses white.
        border = QColor(t.FOCUS_RING if self.hasFocus() else t.BORDER_LIGHT)
        pen_brush = border
        if self._shine >= 0.0:
            band = rect.width() * 0.55
            x = -band + (rect.width() + 2 * band) * self._shine
            glint = QColor(t.TEXT_PRIMARY) if t.is_dark() else QColor(255, 255, 255)
            glint.setAlpha(46 if t.is_dark() else 200)
            clear = QColor(glint)
            clear.setAlpha(0)
            grad = QLinearGradient(x, 0, x + band, rect.height() * 0.35)
            grad.setColorAt(0.0, clear)
            grad.setColorAt(0.5, glint)
            grad.setColorAt(1.0, clear)
            painter.fillPath(shape, grad)
            # The edge catches the same light, in the emphasis value.
            edge = QLinearGradient(x, 0, x + band, rect.height() * 0.35)
            edge.setColorAt(0.0, border)
            edge.setColorAt(0.5, QColor(t.ACCENT))
            edge.setColorAt(1.0, border)
            pen_brush = edge

        painter.setPen(QPen(QBrush(pen_brush), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(shape)

        painter.setPen(QColor(t.TEXT_PRIMARY))
        painter.setFont(self.font())
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        painter.end()

    def retheme(self) -> None:
        self.update()

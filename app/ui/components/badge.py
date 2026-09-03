"""Count badges and status dots.

Badges are the only genuinely pill-shaped things in Unified, which is the
point: when nothing else in the interface is a pill, a pill unambiguously
means "a count".

The count is painted rather than laid out as a QLabel, because a number
that changes should *pop* rather than blink. This is the transitions.dev
"number pop-in": when the value changes, the new number rises from 8px
below through a blur, on a slightly overshooting curve, while the old one
leaves. Unread counts are the one number in a mail client people actually
watch, and a silent swap loses the event.

`StatusDot` pairs a colored dot with a text label rather than using color
alone - a red dot with no words is not an error state, it is a riddle, and
it is invisible to anyone who cannot distinguish it from the green one.
Its label swaps through the "text states swap" transition so a changing
sync phase reads as one line updating, not as flicker.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from app.ui import theme as t
from app.ui.design import motion
from app.ui.design.motion import ValueAnimator, blend

_DOT_SIZE = 8
_MAX_COUNT = 999


class CountBadge(QWidget):
    """An unread/item count. Hidden entirely at zero - a badge reading "0"
    has stopped meaning anything."""

    def __init__(self, tone: str = "quiet", parent=None):
        super().__init__(parent)
        self._tone = tone
        self._count = 0
        self._text = ""
        self._outgoing = ""
        self.setFont(t.make_font("caption_strong"))
        self.setVisible(False)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # 0 -> the new value has fully arrived; 1 -> it is entering.
        self._enter = ValueAnimator(self, 0.0, motion.NUMBER_POP,
                                    motion.EASE_DIGIT)

    # --------------------------------------------------------------- api

    @property
    def count(self) -> int:
        return self._count

    def text(self) -> str:
        return self._text

    def set_count(self, count: int) -> None:
        count = max(0, int(count or 0))
        if count == self._count:
            return
        previous = self._text
        self._count = count
        self._text = "" if not count else (
            str(count) if count <= _MAX_COUNT else f"{_MAX_COUNT}+"
        )
        self.setAccessibleName(f"{count} unread" if count else "")
        self.setVisible(bool(count))
        self.updateGeometry()
        if self._text and previous != self._text:
            self._outgoing = previous
            self._enter.set_now(1.0)
            self._enter.to(0.0)
        self.update()

    def set_tone(self, tone: str) -> None:
        if tone != self._tone:
            self._tone = tone
            self.update()

    # ---------------------------------------------------------- geometry

    def sizeHint(self) -> QSize:  # noqa: N802
        if not self._text:
            return QSize(0, 0)
        metrics = QFontMetrics(self.font())
        width = max(t.SPACE_2XL, metrics.horizontalAdvance(self._text) + t.SPACE_LG)
        return QSize(width, t.CONTROL_XS - 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    # ------------------------------------------------------------- paint

    def _colors(self) -> tuple[QColor, QColor]:
        p = t.theme_manager.palette
        if self._tone == "accent":
            return QColor(p.accent_solid), QColor(p.text_on_accent)
        if self._tone == "quiet":
            return QColor(0, 0, 0, 0), QColor(p.text_tertiary)
        return QColor(p.surface_active), QColor(p.text_secondary)

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        background, foreground = self._colors()

        if background.alpha():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        painter.setFont(self.font())
        enter = self._enter.value

        # The outgoing number leaves upward as the new one rises into
        # place - both moving, so the swap reads as one digit changing.
        if enter > 0.02 and self._outgoing:
            leaving = QColor(foreground)
            leaving.setAlphaF(max(0.0, 1.0 - enter * 1.6))
            painter.setPen(leaving)
            painter.drawText(
                rect.translated(0, -motion.DISTANCE_BASE * enter),
                Qt.AlignmentFlag.AlignCenter, self._outgoing,
            )

        arriving = QColor(foreground)
        arriving.setAlphaF(max(0.0, 1.0 - enter))
        painter.setPen(arriving)
        painter.drawText(
            rect.translated(0, motion.DISTANCE_BASE * enter),
            Qt.AlignmentFlag.AlignCenter, self._text,
        )
        painter.end()


class StatusDot(QWidget):
    """A colored dot plus its explanation. Never the dot on its own."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SPACE_SM)

        self._dot = _StatusLight()
        self._text = QLabel()
        self._text.setProperty("tone", "tertiary")
        self._text.setFont(t.make_font("caption"))
        self._text.setWordWrap(False)
        self._text.setMinimumWidth(0)
        self._text.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        layout.addWidget(self._dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._text, stretch=1)
        self._status = "idle"
        self._full_text = ""
        self.set_status("idle", "")

    def set_status(self, status_key: str, text: str) -> None:
        self._status = status_key
        self._dot.set_status(status_key)
        # Elided here rather than allowed to stretch the sidebar: a
        # provider error can be a paragraph. The full text stays available
        # as a tooltip and in the accessible description.
        self._full_text = text
        self._apply_elided()
        self._text.setToolTip(text)
        self.setAccessibleDescription(f"{status_key}: {text}" if text else status_key)
        self._dot.setVisible(bool(text))
        self.setVisible(bool(text))

    def _apply_elided(self) -> None:
        metrics = QFontMetrics(self._text.font())
        available = max(40, self._text.width() or self.width() - _DOT_SIZE - 12)
        self._text.setText(
            metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, available)
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._apply_elided()
        super().resizeEvent(event)

    def refresh_theme(self) -> None:
        self.set_status(self._status, self._full_text)


class _StatusLight(QWidget):
    """The dot. Painted rather than styled so the color can cross-fade
    between states, and so "syncing" can breathe instead of sitting
    still - a static dot next to moving numbers reads as stalled."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_DOT_SIZE, _DOT_SIZE)
        self._status = "idle"
        self._color = QColor(t.status_color("idle"))
        self._fade = ValueAnimator(self, 1.0, motion.DURATION_FAST,
                                   spatial=False)
        self._from = QColor(self._color)
        self._pulse = ValueAnimator(self, 0.0, motion.SHIMMER_CYCLE // 2,
                                    motion.EASE_IN_OUT)
        self._pulse_up = True

    def set_status(self, status_key: str) -> None:
        if status_key == self._status:
            return
        self._status = status_key
        self._from = QColor(self._color)
        self._color = QColor(t.status_color(status_key))
        self._fade.set_now(0.0)
        self._fade.to(1.0)
        if status_key == "syncing":
            self._start_pulse()
        else:
            self._pulse.stop()
            self._pulse.set_now(0.0)

    def _start_pulse(self) -> None:
        target = 1.0 if self._pulse_up else 0.0
        self._pulse_up = not self._pulse_up
        self._pulse.to(target)
        # Re-arm only while still syncing, so the timer dies with the state.
        from PySide6.QtCore import QTimer

        QTimer.singleShot(
            motion.SHIMMER_CYCLE // 2 + 20,
            lambda: self._start_pulse() if self._status == "syncing" else None,
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = blend(self._from, self._color, self._fade.value)
        if self._status == "syncing":
            color = QColor(color)
            color.setAlphaF(0.55 + 0.45 * self._pulse.value)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(0, 0, _DOT_SIZE, _DOT_SIZE))
        painter.end()

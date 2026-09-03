"""Count badges and status dots.

Badges are the only genuinely pill-shaped things in Unified, which is the
point: when nothing else in the interface is a pill, a pill unambiguously
means "a count". They also cap their own text, because an unread count
that grows to four digits silently steals width from the label it is
supposed to annotate.

`StatusDot` pairs a colored dot with a text label rather than using color
alone - a red dot with no words is not an error state, it is a riddle,
and it is invisible to anyone who cannot distinguish it from the green
one next to it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from app.ui import theme as t

_DOT_SIZE = 8
_MAX_COUNT = 999


class CountBadge(QLabel):
    """An unread/item count. Hidden entirely at zero - a badge reading
    "0" is a badge that has stopped meaning anything."""

    def __init__(self, tone: str = "quiet", parent=None):
        super().__init__(parent)
        self.setProperty("role", "badge")
        self.setProperty("tone", tone)
        self.setFont(t.make_font("caption_strong"))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setVisible(False)
        self._count = 0

    def set_count(self, count: int) -> None:
        self._count = max(0, int(count or 0))
        if not self._count:
            self.setVisible(False)
            self.setText("")
            return
        text = str(self._count) if self._count <= _MAX_COUNT else f"{_MAX_COUNT}+"
        self.setText(text)
        self.setAccessibleName(f"{self._count} unread")
        self.setVisible(True)

    def set_tone(self, tone: str) -> None:
        t.set_variant(self, "tone", tone)


class StatusDot(QWidget):
    """A colored dot plus its explanation. Never the dot on its own."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SPACE_SM)

        self._dot = QLabel()
        self._dot.setFixedSize(_DOT_SIZE, _DOT_SIZE)
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
        color = t.status_color(status_key)
        self._dot.setStyleSheet(
            f"background: {color}; border-radius: {_DOT_SIZE // 2}px;"
        )
        # Elided here rather than allowed to stretch the sidebar: a provider
        # error can be a paragraph long. The full text stays available as a
        # tooltip and in the accessible description.
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
            metrics.elidedText(
                self._full_text, Qt.TextElideMode.ElideRight, available
            )
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._apply_elided()
        super().resizeEvent(event)

    def refresh_theme(self) -> None:
        self.set_status(self._status, self._full_text)

"""The sidebar navigation row.

A folder row has to answer three things at a glance - what it is, how
many unread it holds, and whether it is the one you are looking at - and
the third has to survive being seen out of the corner of your eye while
the pointer happens to be hovering a different row.

So selection is expressed twice: a tinted fill (from the stylesheet) and
a 3px accent bar painted on the leading edge (here, because QSS has no
way to animate a sub-element). A fill on its own reads as hover; the bar
is what makes "active" unambiguous. It grows from zero height rather than
appearing, which is the cheapest possible way to make navigation feel
like it moved rather than teleported - and it collapses to an instant
change when the OS asks for reduced motion.

The count lives in a real `CountBadge` child instead of being appended to
the label text: baking "(12)" into a button's string means it elides
along with the name, and no assistive technology can tell the two apart.

Named `NavPill` for continuity with the pre-redesign codebase; `NavItem`
is the name to use in new code.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QPushButton

from app.ui import theme as t
from app.ui.components.badge import CountBadge
from app.ui.svg_icon import themed

_BAR_WIDTH = 3
_BAR_HEIGHT_RATIO = 0.55


class NavPill(QPushButton):
    def __init__(self, text: str = "", icon: str | None = None, parent=None):
        super().__init__(text, parent)
        self.setObjectName("navItem")
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(t.make_font("nav_label"))
        self.setMinimumHeight(t.TAB_HEIGHT)

        self._icon_name = icon
        if icon:
            self.refresh_icon()

        # The badge is a child laid out on the right, so it can never be
        # elided away with the label or mistaken for part of the name.
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, t.SPACE_MD, 0)
        row.addStretch(1)
        self.badge = CountBadge("quiet")
        row.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._indicator = 1.0 if self.isChecked() else 0.0
        self._anim = QPropertyAnimation(self, b"indicator", self)
        self._anim.setDuration(t.duration(t.DURATION_BASE))
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuint)
        self.toggled.connect(self._on_toggled)

    # ------------------------------------------------------------- state

    def set_count(self, count: int) -> None:
        self.badge.set_count(count)
        self.badge.set_tone("accent" if self.isChecked() and count else "quiet")

    def refresh_icon(self) -> None:
        if not self._icon_name:
            return
        self.setIcon(themed(self._icon_name, t.ICON_MD, "default"))
        self.setIconSize(QSize(t.ICON_MD, t.ICON_MD))

    def _on_toggled(self, checked: bool) -> None:
        self.setFont(t.make_font("nav_label_active" if checked else "nav_label"))
        self.badge.set_tone("accent" if checked and self.badge.text() else "quiet")
        duration = t.duration(t.DURATION_BASE)
        if not duration:
            self._set_indicator(1.0 if checked else 0.0)
            return
        self._anim.stop()
        self._anim.setDuration(duration)
        self._anim.setStartValue(self._indicator)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    # ------------------------------------------------------- animation

    def _get_indicator(self) -> float:
        return self._indicator

    def _set_indicator(self, value: float) -> None:
        self._indicator = value
        self.update()

    indicator = Property(float, _get_indicator, _set_indicator)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._indicator <= 0.001:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(t.qcolor(t.ACCENT))
        full = self.height() * _BAR_HEIGHT_RATIO
        height = full * self._indicator
        painter.drawRoundedRect(
            QRectF(0.0, (self.height() - height) / 2.0, float(_BAR_WIDTH), height),
            1.5, 1.5,
        )
        painter.end()


NavItem = NavPill

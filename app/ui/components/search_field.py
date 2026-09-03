"""Search.

Search in a mail client is not a toolbar decoration; it is how anyone
finds a message older than the last screenful. So it gets a real keyboard
shortcut, real scope, and real feedback about what it is doing - but *not*
a lot of pixels. A search box the size of a hero banner is not "first
class", it is just large.

The field paints its own surface, for two reasons that both showed up on
screen:

* **Qt does not anti-alias a QSS `border-radius`.** A rounded field drawn
  by the stylesheet has visibly stepped corners, and at pill radius it
  looks broken rather than round. Painting it here with
  `RenderHint.Antialiasing` is the only way to get a smooth edge.
* **`addAction(LeadingPosition)` positions the icon itself,** with its own
  margins, on top of whatever padding the stylesheet applies. The result
  was a magnifier stranded near the left edge with a 30px gap before the
  placeholder. Drawing the icon at a known offset and reserving exactly
  that much text margin puts the two where they belong: icon, one gap,
  text.

Painting also buys the field the same animated hover and focus every
other control has, which a stylesheet cannot give it.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLineEdit, QWidget

from app.ui import theme as t
from app.ui.design import motion
from app.ui.design.motion import StateAnimator, blend
from app.ui.svg_icon import tinted_pixmap

_ICON = t.ICON_SM          # the magnifier
_ICON_LEFT = 11            # from the field's left edge to the icon
_ICON_GAP = 8              # from the icon to the first character
_CLEAR_ROOM = 30           # reserved on the right for the clear button


class SearchField(QLineEdit):
    escaped = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("searchField")
        self.setClearButtonEnabled(True)
        self.setPlaceholderText("Search all accounts")
        self.setFont(t.make_font("field_value"))
        self.setFixedHeight(t.CONTROL_MD)
        self.setAccessibleName("Search mail")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        # The stylesheet draws nothing for this field; paintEvent does.
        self.setProperty("painted", "true")
        # Exactly the room the painted icon occupies, so the text starts
        # one gap after it instead of wherever Qt felt like.
        self.setTextMargins(
            _ICON_LEFT + _ICON + _ICON_GAP - 4, 0, _CLEAR_ROOM, 0
        )

        self._anim = StateAnimator(
            self, hover=motion.DURATION_HOVER, focus=motion.DURATION_HOVER,
        )
        self.textChanged.connect(lambda _text: self.update())

    # ------------------------------------------------------------- theme

    def refresh_icon(self) -> None:
        self.update()

    # ------------------------------------------------------------ events

    def enterEvent(self, event) -> None:  # noqa: N802
        self._anim.to("hover", 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._anim.to("hover", 0.0, exiting=True)
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._anim.to("focus", 1.0)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._anim.to("focus", 0.0, exiting=True)
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self.text():
                self.clear()
            self.escaped.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        palette = t.theme_manager.palette
        hover = self._anim["hover"]
        focus = self._anim["focus"]

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # A true pill: the radius is half the height, computed rather than
        # left to a 999px value the style engine has to interpret.
        radius = rect.height() / 2

        fill = blend(palette.surface_hover, palette.surface_active, hover * 0.5)
        fill = blend(fill, QColor(palette.surface), focus)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)

        border = blend(
            QColor(0, 0, 0, 0), QColor(palette.border), max(hover, 0.0) * 0.9
        )
        border = blend(border, QColor(palette.focus_ring), focus)
        if border.alpha():
            painter.setPen(QPen(border, 1 + focus))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

        # The magnifier, at a known offset. It brightens as the field wakes
        # up, so the whole control reads as one thing responding.
        tint = blend(palette.text_tertiary, palette.text_secondary,
                     max(hover, focus))
        painter.drawPixmap(
            _ICON_LEFT, int((self.height() - _ICON) / 2),
            tinted_pixmap("search", _ICON, tint.name()),
        )
        painter.end()

        # Qt draws the text, selection, cursor and clear button on top.
        super().paintEvent(event)

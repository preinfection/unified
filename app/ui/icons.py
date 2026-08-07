"""Programmatically drawn monochrome app icon (no binary assets required).

Each icon size is drawn fresh rather than scaling one large pixmap down:
a stroke width that is proportionally thin at 256px (e.g. 10px) becomes
sub-pixel and all but disappears once Windows shrinks it to a 16-24px
taskbar or title-bar icon. Keeping a flat minimum stroke width at every
size keeps the envelope shape legible everywhere it's actually seen.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap

# Sizes Windows actually requests for a window/taskbar/tray icon.
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _draw_icon(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = max(1, round(size * 0.08))
    body = QRect(margin, round(size * 0.25), size - 2 * margin, round(size * 0.5))

    # A flat minimum (not size-proportional) stroke width is what keeps
    # this visible at 16-24px - size * 0.09 alone would round to 0-1px.
    stroke = max(2, round(size * 0.09))
    pen = QPen(Qt.GlobalColor.black, stroke)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.GlobalColor.white)
    radius = max(1, round(size * 0.03))
    painter.drawRoundedRect(body, radius, radius)

    painter.drawLine(body.topLeft(), body.center())
    painter.drawLine(body.topRight(), body.center())

    painter.end()
    return pixmap


def make_app_icon(size: int = 256) -> QIcon:
    """Multi-resolution black-and-white envelope icon for window/taskbar/tray."""
    icon = QIcon()
    for s in ICON_SIZES:
        icon.addPixmap(_draw_icon(s))
    if size not in ICON_SIZES:
        icon.addPixmap(_draw_icon(size))
    return icon

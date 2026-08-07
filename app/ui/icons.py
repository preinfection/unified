"""Programmatically drawn monochrome app icon (no binary assets required)."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap


def make_app_icon(size: int = 256) -> QIcon:
    """Draw a simple black-and-white envelope icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = size // 8
    body = QRect(margin, size // 4, size - 2 * margin, size // 2)

    pen = QPen(Qt.GlobalColor.black, max(2, size // 24))
    painter.setPen(pen)
    painter.setBrush(Qt.GlobalColor.white)
    painter.drawRoundedRect(body, size // 32, size // 32)

    # Envelope flap
    painter.drawLine(body.topLeft(), body.center())
    painter.drawLine(body.topRight(), body.center())

    painter.end()
    return QIcon(pixmap)

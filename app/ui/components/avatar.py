"""Shared "initial letter in a colored circle" avatar painting.

Used by both the sidebar's AccountItem and the email list's row delegate,
so a given address always gets the same color in both places. Colors are
a small muted, desaturated palette (not a rainbow) - enough to help tell
correspondents apart at a glance without turning the list into confetti,
which is exactly the kind of "unnecessary effect" the design brief warns
against.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter

_PALETTE = [
    "#5b8def",  # blue (same family as the accent)
    "#4fb0a5",  # teal
    "#8b7ce0",  # violet
    "#d98a4f",  # amber-brown
    "#5fb37a",  # green
    "#c47ba0",  # mauve
]


def avatar_color(key: str) -> QColor:
    if not key:
        return QColor(_PALETTE[0])
    return QColor(_PALETTE[hash(key) % len(_PALETTE)])


def initial_letter(name: str, email: str) -> str:
    source = (name or email or "?").strip()
    return source[0].upper() if source else "?"


def paint_avatar(
    painter: QPainter, rect: QRectF, key: str, name: str, email: str
) -> None:
    """Paint a filled circle with a centered initial letter into rect."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(avatar_color(key))
    painter.drawEllipse(rect)

    font = QFont(painter.font())
    font.setPixelSize(max(10, int(rect.height() * 0.42)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, initial_letter(name, email))
    painter.restore()

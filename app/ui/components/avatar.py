"""Correspondent avatars: an initial in a colored disc.

Shared by the sidebar's account rows, the message list delegate and the
reading pane header, so one address always looks the same everywhere in
the window - which is the only reason a color-coded avatar is worth
having at all.

Two details that matter more than they look:

* The hue is chosen with a stable digest of the address, not Python's
  `hash()`. String hashing is randomized per process (PYTHONHASHSEED),
  so a `hash()`-derived palette index gives the same person a different
  color on every launch - which quietly destroys the recognition the
  avatar exists to provide.
* The palette is six to eight muted hues, not a rainbow, and every hue
  is paired with a foreground chosen for contrast rather than assumed to
  be white. An inbox is a dense grid of these; saturated color here
  reads as noise and competes with the unread indicator, which is the
  one thing in a row that genuinely needs to shout.
"""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from app.ui import theme as t
from app.ui.design.palette import contrast_ratio


def _stable_index(key: str, count: int) -> int:
    digest = hashlib.blake2b(key.strip().lower().encode("utf-8"), digest_size=4)
    return int.from_bytes(digest.digest(), "big") % count


def avatar_color(key: str) -> QColor:
    hues = t.theme_manager.palette.avatar_hues
    if not key:
        return QColor(hues[0])
    return QColor(hues[_stable_index(key, len(hues))])


def avatar_foreground(background: QColor) -> QColor:
    """White or near-black, whichever actually reads on this disc."""
    bg = background.name()
    white, ink = "#ffffff", "#101216"
    return QColor(white if contrast_ratio(white, bg) >= contrast_ratio(ink, bg) else ink)


def initial_letter(name: str, email: str) -> str:
    source = (name or email or "?").strip()
    for char in source:
        if char.isalnum():
            return char.upper()
    return "?"


def paint_avatar(
    painter: QPainter,
    rect: QRectF,
    key: str,
    name: str,
    email: str,
    *,
    dimmed: bool = False,
) -> None:
    """Paint a filled disc with a centered initial into `rect`."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    fill = avatar_color(key)
    if dimmed:
        # A read message's avatar recedes rather than disappearing: the
        # row still needs the identity cue, just not at full strength.
        fill = QColor(fill)
        fill.setAlpha(190)
    painter.setBrush(fill)
    painter.drawEllipse(rect)

    font = QFont(painter.font())
    font.setFamilies(t.FONT_FAMILIES)
    font.setPixelSize(max(9, int(rect.height() * 0.42)))
    font.setWeight(QFont.Weight(t.WEIGHT_SEMIBOLD))
    painter.setFont(font)
    painter.setPen(avatar_foreground(fill))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, initial_letter(name, email))
    painter.restore()


class Avatar(QWidget):
    """The painted disc as a widget, for layouts that need one."""

    def __init__(self, size: int = t.AVATAR_MD, parent=None):
        super().__init__(parent)
        self._size = size
        self._name = ""
        self._email = ""
        self.setFixedSize(size, size)

    def set_identity(self, name: str, email: str) -> None:
        if (name, email) == (self._name, self._email):
            return
        self._name, self._email = name, email
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._size, self._size)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        paint_avatar(
            painter, QRectF(0, 0, self._size, self._size),
            self._email or self._name, self._name, self._email,
        )

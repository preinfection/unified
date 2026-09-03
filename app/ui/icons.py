"""The application mark, drawn in code at every size Windows asks for.

One mark, used everywhere: the window icon, the taskbar, the tray, the
title bar, the installer, the splash, and the lockup in the command bar.
Having the OS icon and the in-app mark be two different drawings is how a
product ends up not recognisable as itself.

The mark is a filled rounded tile with the envelope flap and a line
knocked out of it. Filled, not stroked, because that is what survives:
the previous mark was an outlined padlock whose strokes went sub-pixel
below about 24px and read as a pale smudge in the taskbar. A solid shape
has no thin parts to lose.

Knocking the flap *out* rather than painting it in a second colour means
the mark self-contrasts: on a light taskbar the flap reads light, on a
dark one it reads dark, and the tile carries the brand colour either way.
No light/dark variants to keep in sync.

Every size is drawn fresh rather than scaled from one large pixmap, so
the corner radius, the flap thickness and the margins stay optically
right at 16px as well as at 256px.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap

# Sizes Windows actually requests for a window/taskbar/tray icon.
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# The OS icon cannot follow the app's theme - it is drawn once, into a
# .ico, and shown on a taskbar whose colour this app does not control.
# So it uses a fixed brand blue that holds up on both a light and a dark
# taskbar, sitting between the two themes' accents rather than matching
# either exactly.
BRAND_MARK = "#3f8ef0"


def _mark_path(size: int) -> tuple[QPainterPath, QPainterPath]:
    """(tile, knockout) for a mark drawn into a `size` x `size` box."""
    inset = size * 0.02
    box = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    radius = box.width() * 0.28

    tile = QPainterPath()
    tile.addRoundedRect(box, radius, radius)

    # Below this the flap and the bar are too close to stay apart, so the
    # bar is dropped and the flap alone carries the mark. Detail that
    # merges into a blur is worse than no detail: it just makes the tile
    # look smudged.
    detailed = size >= 24

    # The flap: a wide, shallow V. Shallow on purpose - a deep V reads as
    # a chevron rather than as the fold of an envelope. The thickness has
    # a flat pixel floor as well as a percentage, because a percentage
    # alone goes sub-pixel at 16px and the knockout disappears.
    pad = box.width() * (0.20 if detailed else 0.17)
    top = box.top() + box.height() * (0.30 if detailed else 0.32)
    mid = box.top() + box.height() * (0.58 if detailed else 0.64)
    thickness = max(2.0, box.width() * (0.115 if detailed else 0.135))

    knockout = QPainterPath()
    knockout.moveTo(box.left() + pad, top)
    knockout.lineTo(box.center().x(), mid)
    knockout.lineTo(box.right() - pad, top)
    knockout.lineTo(box.right() - pad, top + thickness)
    knockout.lineTo(box.center().x(), mid + thickness)
    knockout.lineTo(box.left() + pad, top + thickness)
    knockout.closeSubpath()

    if not detailed:
        return tile, knockout

    # A shorter bar below it reads as the body of the letter.
    line_y = mid + thickness * 2.0
    body = QPainterPath()
    body.addRoundedRect(
        QRectF(box.left() + pad, line_y, box.width() - 2 * pad, thickness),
        thickness / 2, thickness / 2,
    )
    return tile, knockout.united(body)


def make_mark(size: int, ink: str) -> QPixmap:
    """The mark at `size`, in `ink`, with the flap knocked out to
    transparent. Used in-app, where `ink` is the active theme's accent."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    tile, knockout = _mark_path(size)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ink))
    painter.drawPath(tile.subtracted(knockout))
    painter.end()
    return pixmap


def _draw_icon(size: int) -> QPixmap:
    """One size of the OS icon. Kept under this name because build.py
    renders each size through it when assembling the multi-size .ico."""
    return make_mark(size, BRAND_MARK)


def make_app_icon(size: int = 256) -> QIcon:
    """The multi-resolution window/taskbar/tray icon.

    The same mark the command bar shows, so the thing in the taskbar and
    the thing in the window are recognisably one product.
    """
    icon = QIcon()
    for s in ICON_SIZES:
        icon.addPixmap(_draw_icon(s))
    if size not in ICON_SIZES:
        icon.addPixmap(_draw_icon(size))
    return icon

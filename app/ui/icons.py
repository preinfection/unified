"""Programmatically drawn monochrome app icon (no binary assets required).

A padlock where the shackle *is* a bold "U" - not a separate letterform
placed on top of a generic lock glyph, but the same stroke that would
normally just be a plain wire loop, shaped and weighted to read as both
a shackle and a U at once. The legs run down into the lock body rather
than merely touching it, so the two pieces read as one continuous mark.

Each icon size is drawn fresh rather than scaling one large pixmap down:
a stroke width that is proportionally thin at 256px becomes sub-pixel
and all but disappears once Windows shrinks it to a 16-24px taskbar or
title-bar icon. Both the stroke width AND the gap inside the U use a
flat pixel minimum (not a pure percentage) for the same reason - a
percentage-only gap shrinks to sub-pixel at 16px and the two legs merge
into a solid blob instead of reading as a U.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

# Sizes Windows actually requests for a window/taskbar/tray icon.
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _u_shape(x: float, top: float, width: float, height: float, stroke: float) -> QPainterPath:
    """A filled "U" silhouette (straight sides, rounded bottom, open top):
    an outer rounded-bottom shape minus a smaller inner one, built from
    plain rects/ellipses and boolean ops rather than arcTo(), which needs
    no reasoning about Qt's angle-sweep direction to get right.
    """
    def rounded_bottom(rx: float, rtop: float, rw: float, rheight: float) -> QPainterPath:
        radius = rw / 2
        straight_h = max(0.0, rheight - radius)
        p = QPainterPath()
        p.addRect(QRectF(rx, rtop, rw, straight_h))
        p2 = QPainterPath()
        p2.addEllipse(QRectF(rx, rtop + rheight - 2 * radius, rw, 2 * radius))
        return p.united(p2)

    outer = rounded_bottom(x, top, width, height)
    inner = rounded_bottom(x + stroke, top, width - 2 * stroke, height - stroke)
    return outer.subtracted(inner)


def _draw_icon(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = max(1.0, size * 0.08)
    content = size - 2 * margin

    # Lock body: a wide-ish rounded rectangle, not the near-2:1 elongated
    # bar the previous envelope shape used - closer to square reads as
    # properly centered rather than stretched inside a square canvas.
    body_stroke = max(1.0, round(size * 0.05))
    body_w = content * 0.80
    body_h = content * 0.56
    body_x = (size - body_w) / 2
    # Qt draws a path's stroke centered on it, so the visible bottom edge
    # of the body's outline would otherwise overshoot past `margin` by
    # half the stroke width - inset the path itself so the *painted*
    # edge, not the path, lands on the same margin the U's top uses.
    body_y = size - margin - body_stroke / 2 - body_h
    body_radius = body_w * 0.14

    # A flat minimum (not size-proportional) stroke width and U-gap are
    # what keep this legible at 16-24px - pure percentages round to 0-1px
    # and the shape collapses into a blob.
    stroke = max(2.0, round(size * 0.11))
    min_gap = max(2.0, size * 0.09)
    u_width = max(body_w * 0.50, 2 * stroke + min_gap)
    u_x = (size - u_width) / 2
    u_top = margin
    # Legs run a little way into the body rather than just meeting its
    # top edge, so the shackle and body read as one continuous silhouette
    # instead of two shapes that happen to touch.
    u_height = body_y - margin + stroke * 0.5

    shackle = _u_shape(u_x, u_top, u_width, u_height, stroke)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(Qt.GlobalColor.black)
    painter.drawPath(shackle)

    painter.setPen(QPen(Qt.GlobalColor.black, body_stroke))
    painter.setBrush(Qt.GlobalColor.white)
    painter.drawRoundedRect(QRectF(body_x, body_y, body_w, body_h), body_radius, body_radius)

    painter.end()
    return pixmap


def make_mark(size: int, color: str) -> QPixmap:
    """The same padlock-U silhouette in a single color, for use *inside*
    the app (the command bar lockup, the startup window).

    The two-tone window/taskbar icon is built to survive any wallpaper, so
    it carries a white lock body - which at 20px on a dark command bar
    reads as a small white block rather than as a mark. A monochrome
    version tinted from the palette is the right thing on a surface whose
    color the app already controls.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    ink = QColor(color)

    margin = max(1.0, size * 0.06)
    content = size - 2 * margin
    body_stroke = max(1.0, size * 0.09)
    body_w = content * 0.82
    body_h = content * 0.54
    body_x = (size - body_w) / 2
    body_y = size - margin - body_stroke / 2 - body_h
    body_radius = body_w * 0.16

    stroke = max(1.5, size * 0.115)
    min_gap = max(1.5, size * 0.10)
    u_width = max(body_w * 0.52, 2 * stroke + min_gap)
    u_x = (size - u_width) / 2
    u_height = body_y - margin + stroke * 0.5

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    painter.drawPath(_u_shape(u_x, margin, u_width, u_height, stroke))

    painter.setPen(QPen(ink, body_stroke))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(
        QRectF(body_x, body_y, body_w, body_h), body_radius, body_radius
    )
    painter.end()
    return pixmap


def make_app_icon(size: int = 256) -> QIcon:
    """Multi-resolution black-and-white U-in-padlock icon for window/
    taskbar/tray. White fill + black stroke (not a single solid color)
    is deliberate: it self-contrasts against both light and dark
    backgrounds without needing separate light/dark variants."""
    icon = QIcon()
    for s in ICON_SIZES:
        icon.addPixmap(_draw_icon(s))
    if size not in ICON_SIZES:
        icon.addPixmap(_draw_icon(size))
    return icon

"""Real SVG icon loading, tinting, and caching.

Every icon in the app is a real vector asset under assets/icons/ - never a
Unicode symbol or emoji standing in for a control. Source SVGs are drawn
in black (fill or stroke, whichever suits the shape); at load time each is
rasterized once per (name, size, color) and recolored via QPainter's
SourceIn composition mode, so the same file serves every theme color the
app needs (secondary/primary/accent/disabled) without maintaining
separate colored copies on disk.

icon_set() builds a QIcon with distinct pixmaps for Qt's own Normal/
Active/Disabled/Selected icon modes, so hover, pressed/checked, and
disabled states are handled by Qt's normal icon-mode machinery rather
than by hand in each widget.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ICONS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"


@lru_cache(maxsize=None)
def _renderer(name: str) -> QSvgRenderer:
    path = _ICONS_DIR / f"{name}.svg"
    if not path.exists():
        raise FileNotFoundError(f"Missing icon asset: {path}")
    return QSvgRenderer(str(path))


@lru_cache(maxsize=None)
def tinted_pixmap(name: str, size: int, color: str) -> QPixmap:
    """Rasterize icon `name` at `size`x`size`, recolored to `color`."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _renderer(name).render(painter)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return pixmap


# Extra rasterizations every QIcon carries beside its 1x pixmap.
#
# WHY. tinted_pixmap renders at the LOGICAL size, and a QIcon holding only
# that pixmap is upscaled on a 125%, 150% or 200% display - which is what
# most Windows laptops run at - so every glyph in the app was being drawn
# soft. QIcon picks the closest pixmap for size x devicePixelRatio and
# scales DOWN from a larger one cleanly, so one 2x variant covers every
# common scale factor for the cost of a few kilobytes per icon.
_DENSITIES = (1, 2)


def _add(icon: QIcon, name: str, size: int, color: str,
         mode: QIcon.Mode = QIcon.Mode.Normal,
         state: QIcon.State = QIcon.State.Off) -> None:
    for density in _DENSITIES:
        icon.addPixmap(tinted_pixmap(name, size * density, color), mode, state)


def paint_icon(painter: QPainter, name: str, rect: QRectF, color: str) -> None:
    """Draw an icon straight into `rect`, sharp at any size and any scale.

    For glyphs whose size is not fixed - the dock's magnified icons grow
    continuously - a pixmap made at one size would be resampled on every
    frame. This rasterizes at the PHYSICAL size the rect will occupy on
    this painter's device, so a glyph is crisp at 100% and at 200% and at
    every fractional size in between, and the cache keeps a moving glyph
    from re-rendering the SVG on every frame.
    """
    device = painter.device()
    dpr = device.devicePixelRatioF() if device is not None else 1.0
    physical = max(1, round(rect.width() * dpr))
    pixmap = tinted_pixmap(name, physical, color)
    painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))


def icon_set(
    name: str,
    size: int,
    *,
    normal: str,
    active: str | None = None,
    selected: str | None = None,
    disabled: str | None = None,
) -> QIcon:
    """Build a QIcon whose color changes with Qt's own icon Mode - hover
    uses Active, checked/pressed uses Selected, disabled uses Disabled -
    so widgets get correct state colors for free from Qt's style engine.
    """
    icon = QIcon()
    _add(icon, name, size, normal, QIcon.Mode.Normal)
    if active:
        _add(icon, name, size, active, QIcon.Mode.Active)
    if selected:
        _add(icon, name, size, selected, QIcon.Mode.Selected)
        # QIcon.On maps checkable-button "checked" through Selected-like
        # coloring too, for engines that key off State rather than Mode.
        _add(icon, name, size, selected, QIcon.Mode.Normal, QIcon.State.On)
    if disabled:
        _add(icon, name, size, disabled, QIcon.Mode.Disabled)
    return icon


def simple_icon(name: str, size: int, color: str) -> QIcon:
    """A single-color QIcon with no per-mode variation - for places (e.g.
    a static label icon) where the icon's color never needs to change."""
    icon = QIcon()
    _add(icon, name, size, color)
    return icon

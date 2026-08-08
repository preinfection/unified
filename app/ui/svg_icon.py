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

from PySide6.QtCore import QSize, Qt
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
    icon.addPixmap(tinted_pixmap(name, size, normal), QIcon.Mode.Normal)
    if active:
        icon.addPixmap(tinted_pixmap(name, size, active), QIcon.Mode.Active)
    if selected:
        icon.addPixmap(tinted_pixmap(name, size, selected), QIcon.Mode.Selected)
        # QIcon.On maps checkable-button "checked" through Selected-like
        # coloring too, for engines that key off State rather than Mode.
        icon.addPixmap(tinted_pixmap(name, size, selected), QIcon.Mode.Normal,
                       QIcon.State.On)
    if disabled:
        icon.addPixmap(tinted_pixmap(name, size, disabled), QIcon.Mode.Disabled)
    return icon


def simple_icon(name: str, size: int, color: str) -> QIcon:
    """A single-color QIcon with no per-mode variation - for places (e.g.
    a static label icon) where the icon's color never needs to change."""
    icon = QIcon()
    icon.addPixmap(tinted_pixmap(name, size, color))
    return icon

"""Real SVG icon loading, tinting, and caching.

Every icon in the app is a real vector asset under assets/icons/ - never a
Unicode symbol or emoji standing in for a control. Source SVGs are drawn
in black (fill or stroke, whichever suits the shape); at load time each is
rasterized once per (name, size, color) and recolored via QPainter's
SourceIn composition mode, so the same file serves every theme color the
app needs without maintaining separate colored copies on disk.

Three layers, in the order a caller should reach for them:

* `themed(name, size, role)` - the normal case. Colors come from the
  active palette by *role*, and the QIcon carries per-state pixmaps, so
  hover/checked/disabled are handled by Qt's own icon-mode machinery
  rather than by hand at each call site.
* `icon_set` / `simple_icon` - explicit colors, for the few places that
  legitimately need one (a status dot that is always the danger color).
* `theme_asset_url` - a real PNG on disk, for the two QSS subcontrols
  (combo chevron, checkbox tick) that can only take an `image: url(...)`.

The pixmap cache is keyed by color, so a theme switch simply produces new
entries rather than needing invalidation; icons rebuilt after a switch
pick up the new palette on their next `themed()` call.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ICONS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"

# Role -> the palette attribute an icon in that role is tinted with.
# "quiet" is the default for anything that is not the focus of attention.
_ICON_ROLE_COLORS = {
    "quiet": ("text_tertiary", "text_primary", "accent", "text_disabled"),
    "default": ("text_secondary", "text_primary", "accent", "text_disabled"),
    "strong": ("text_primary", "text_primary", "accent", "text_disabled"),
    "accent": ("accent", "accent_hover", "accent", "text_disabled"),
    "on_accent": ("text_on_accent", "text_on_accent", "text_on_accent", "text_disabled"),
    "danger": ("danger_fg", "danger_fg", "danger_fg", "text_disabled"),
    "warning": ("warning_fg", "warning_fg", "warning_fg", "text_disabled"),
    "success": ("success_fg", "success_fg", "success_fg", "text_disabled"),
    "star": ("star", "star", "star", "text_disabled"),
}


@lru_cache(maxsize=None)
def _renderer(name: str) -> QSvgRenderer:
    path = _ICONS_DIR / f"{name}.svg"
    if not path.exists():
        raise FileNotFoundError(f"Missing icon asset: {path}")
    return QSvgRenderer(str(path))


def available_icons() -> list[str]:
    return sorted(p.stem for p in _ICONS_DIR.glob("*.svg"))


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
    """A QIcon whose color follows Qt's own icon Mode - hover uses Active,
    checked/pressed uses Selected, disabled uses Disabled - so widgets get
    correct state colors from the style engine instead of from bespoke
    per-widget code."""
    icon = QIcon()
    icon.addPixmap(tinted_pixmap(name, size, normal), QIcon.Mode.Normal)
    if active:
        icon.addPixmap(tinted_pixmap(name, size, active), QIcon.Mode.Active)
    if selected:
        icon.addPixmap(tinted_pixmap(name, size, selected), QIcon.Mode.Selected)
        # Some style engines key checkable "checked" off State rather than
        # Mode; register both so a checked toolbar button is never left
        # with its resting color.
        icon.addPixmap(tinted_pixmap(name, size, selected), QIcon.Mode.Normal,
                       QIcon.State.On)
    if disabled:
        icon.addPixmap(tinted_pixmap(name, size, disabled), QIcon.Mode.Disabled)
    return icon


def simple_icon(name: str, size: int, color: str) -> QIcon:
    """A single-color QIcon with no per-mode variation - for a static
    label glyph whose color never changes."""
    icon = QIcon()
    icon.addPixmap(tinted_pixmap(name, size, color))
    return icon


def themed(name: str, size: int, role: str = "default") -> QIcon:
    """The normal way to ask for an icon: by semantic role, resolved
    against whatever theme is active right now."""
    from app.ui.design.theme import theme_manager

    palette = theme_manager.palette
    normal, active, selected, disabled = _ICON_ROLE_COLORS[role]
    return icon_set(
        name, size,
        normal=palette.color(normal),
        active=palette.color(active),
        selected=palette.color(selected),
        disabled=palette.color(disabled),
    )


def themed_pixmap(name: str, size: int, role: str = "default") -> QPixmap:
    """A single tinted pixmap in the active theme, for label glyphs and
    hand-painted delegates."""
    from app.ui.design.theme import theme_manager

    return tinted_pixmap(
        name, size, theme_manager.palette.color(_ICON_ROLE_COLORS[role][0])
    )


_asset_cache: dict[tuple[str, int, str], str] = {}


def theme_asset_url(name: str, size: int, color: str) -> str:
    """A tinted PNG on disk, as a URL for QSS `image:` properties.

    QSS cannot draw a shape, and Qt's Fusion style silently drops the
    native QComboBox arrow once any subcontrol is styled - so the arrow
    has to come back as a real image file. Written once per
    (name, size, color) into the temp directory and reused; a theme
    switch requests a different color and therefore a different file.
    """
    key = (name, size, color)
    cached = _asset_cache.get(key)
    if cached is not None:
        return cached

    safe = color.lstrip("#")
    path = Path(tempfile.gettempdir()) / f"unified_{name}_{size}_{safe}.png"
    if not path.exists():
        tinted_pixmap(name, size, color).save(str(path), "PNG")
    url = path.as_posix()
    _asset_cache[key] = url
    return url

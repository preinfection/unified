"""Buttons: one control, several appearances.

The temptation in a Qt redesign is to paint a custom clickable QWidget
for every button style. That loses keyboard activation, focus, the
accessibility tree, `setDefault`, `QDialogButtonBox` participation and
platform behavior - all of which have to be reimplemented badly. So every
button here *is* a `QPushButton`; what changes is a dynamic property the
stylesheet selects on:

    variant : primary | secondary | subtle | danger | danger_quiet | link
    size    : sm | md | lg
    shape   : icon        (square, label-less)

That means "make this button destructive" is a property change, and every
state (hover, pressed, focus, checked, disabled) comes from one place in
the stylesheet instead of five ad-hoc `setStyleSheet` calls.

Icons are set by *role* rather than by color, so a button's icon follows
the theme and its own interaction state without the call site knowing
which hex value is current.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QPushButton, QToolButton

from app.ui import theme as t
from app.ui.svg_icon import themed

VARIANT_PRIMARY = "primary"
VARIANT_SECONDARY = "secondary"
VARIANT_SUBTLE = "subtle"
VARIANT_DANGER = "danger"
VARIANT_DANGER_QUIET = "danger_quiet"
VARIANT_LINK = "link"

_ICON_ROLE_FOR_VARIANT = {
    VARIANT_PRIMARY: "on_accent",
    VARIANT_SECONDARY: "default",
    VARIANT_SUBTLE: "default",
    VARIANT_DANGER: "on_accent",
    VARIANT_DANGER_QUIET: "danger",
    VARIANT_LINK: "accent",
}

_ICON_SIZE_FOR_SIZE = {"sm": t.ICON_SM, "md": t.ICON_MD, "lg": t.ICON_MD}


class Button(QPushButton):
    """The app's button. Everything else here is a thin preset of it."""

    def __init__(
        self,
        text: str = "",
        *,
        variant: str = VARIANT_SECONDARY,
        size: str = "md",
        icon: str | None = None,
        icon_role: str | None = None,
        tooltip: str = "",
        parent=None,
    ):
        super().__init__(text, parent)
        self._variant = variant
        self._size = size
        self._icon_name = icon
        self._icon_role = icon_role or _ICON_ROLE_FOR_VARIANT.get(variant, "default")
        self.setProperty("variant", variant)
        self.setProperty("size", size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(t.make_font("button_sm" if size == "sm" else "button"))
        if tooltip:
            self.setToolTip(tooltip)
        if icon:
            self.refresh_icon()

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        self._icon_role = _ICON_ROLE_FOR_VARIANT.get(variant, "default")
        t.set_variant(self, "variant", variant)
        self.refresh_icon()

    def set_icon(self, name: str | None, role: str | None = None) -> None:
        self._icon_name = name
        if role:
            self._icon_role = role
        self.refresh_icon()

    def refresh_icon(self) -> None:
        """Re-tint the icon for the current theme. Called on construction
        and again whenever the palette changes."""
        if not self._icon_name:
            return
        size = _ICON_SIZE_FOR_SIZE.get(self._size, t.ICON_MD)
        self.setIcon(themed(self._icon_name, size, self._icon_role))
        self.setIconSize(QSize(size, size))


class PrimaryButton(Button):
    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("variant", VARIANT_PRIMARY)
        super().__init__(text, **kwargs)


class DangerButton(Button):
    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("variant", VARIANT_DANGER)
        super().__init__(text, **kwargs)


class SubtleButton(Button):
    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("variant", VARIANT_SUBTLE)
        super().__init__(text, **kwargs)


class LinkButton(Button):
    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("variant", VARIANT_LINK)
        super().__init__(text, **kwargs)


class IconButton(Button):
    """A square, label-less action. Always carries a tooltip: an icon
    with no accessible name is a puzzle, not a control."""

    def __init__(
        self,
        icon: str,
        tooltip: str,
        *,
        size: str = "md",
        icon_role: str = "default",
        checkable: bool = False,
        parent=None,
    ):
        super().__init__(
            "", variant=VARIANT_SUBTLE, size=size, icon=icon,
            icon_role=icon_role, tooltip=tooltip, parent=parent,
        )
        self.setProperty("shape", "icon")
        self.setCheckable(checkable)
        self.setAccessibleName(tooltip)


class AccentButton(Button):
    """The product's primary action.

    Kept as its own class (rather than folded into `Button`) because
    "this is *the* action on this surface" is a design statement worth
    naming, and because the compose/send/save call sites read better for
    it. It is a plain primary Button underneath - no custom painting, so
    it keeps focus, keyboard activation and default-button behavior.
    """

    def __init__(self, text: str = "", parent=None, **kwargs):
        kwargs.setdefault("variant", VARIANT_PRIMARY)
        kwargs.setdefault("size", "lg")
        super().__init__(text, parent=parent, **kwargs)


class ToolIconButton(QToolButton):
    """A QToolButton for the few places Qt wants one (menu popups with an
    indicator). Same visual contract as IconButton."""

    def __init__(self, icon: str, tooltip: str, *, size: str = "md", parent=None):
        super().__init__(parent)
        self._icon_name = icon
        self._size = size
        self.setProperty("variant", VARIANT_SUBTLE)
        self.setProperty("shape", "icon")
        self.setProperty("size", size)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_icon()

    def refresh_icon(self) -> None:
        size = _ICON_SIZE_FOR_SIZE.get(self._size, t.ICON_MD)
        self.setIcon(themed(self._icon_name, size, "default"))
        self.setIconSize(QSize(size, size))


def refresh_button_icons(root) -> None:
    """Re-tint every themed icon under `root` after a theme change.

    Icons are rasterized pixmaps, so unlike QSS colors they do not update
    themselves when the palette swaps. Walking the tree once per theme
    switch is far cheaper than every button subscribing to a signal.
    """
    for widget in root.findChildren(object):
        refresh = getattr(widget, "refresh_icon", None)
        if callable(refresh):
            refresh()

"""Buttons.

Two problems with the previous version, both of which a user names on
sight: they were flat rectangles with a grey 1px border, and they snapped
between states, because Qt Style Sheets have no `transition`. A
stylesheet-only button in Qt cannot feel like anything.

So these paint themselves. Every button is still a real `QPushButton` -
keyboard activation, focus, `setDefault`, the accessibility tree and
`QDialogButtonBox` participation all survive, which a hand-rolled
clickable `QWidget` throws away - but `paintEvent` draws the surface and a
`StateAnimator` interpolates between states instead of cutting.

What that buys, concretely:

* **Press physics.** The whole button scales to 0.972 and settles back.
  This is the single detail that makes an interface feel like it is
  listening; a color swap does not.
* **Hover that arrives.** 130ms toward the hover surface, so moving along
  a toolbar reads as one continuous motion instead of a strobe.
* **Material.** A filled control gets a top-down value shift and a 1px
  inner highlight along its top edge - what a surface catching light from
  above actually looks like. A flat fill plus a grey outline is a
  wireframe of a button, not a button.
* **A focus ring that moves nothing.** Drawn *outside* the button's rect
  rather than by thickening its border, so tabbing along a row does not
  shuffle it sideways.

Appearance is still a dynamic property (`variant`), so "make this
destructive" stays a one-line change, and the stylesheet keeps ownership
of the things it is good at: font, padding for non-painted controls, and
the disabled text color.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QPushButton, QToolButton

from app.ui import theme as t
from app.ui.design import motion
from app.ui.design.motion import StateAnimator, ValueAnimator, blend, lerp

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

_ROLE_COLOR = {
    "on_accent": "text_on_accent",
    "danger": "danger_fg",
    "star": "star",
    "warning": "warning_fg",
    "success": "success_fg",
    "accent": "accent_fg",
}

_ICON_SIZE_FOR_SIZE = {"sm": t.ICON_SM, "md": t.ICON_MD, "lg": t.ICON_MD}
_HEIGHT_FOR_SIZE = {"sm": t.CONTROL_SM, "md": t.CONTROL_MD, "lg": t.CONTROL_LG}
_PAD_FOR_SIZE = {"sm": t.SPACE_LG, "md": t.SPACE_XL, "lg": t.SPACE_2XL}

# How far a pressed button scales down: small enough to read as pressure
# rather than as the button shrinking.
_PRESS_SCALE = 0.972


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
        self._square = False

        self.setProperty("variant", variant)
        self.setProperty("size", size)
        self.setProperty("painted", "true")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(t.make_font("button_sm" if size == "sm" else "button"))
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if tooltip:
            self.setToolTip(tooltip)

        self._anim = StateAnimator(
            self,
            hover=motion.DURATION_HOVER,
            press=motion.DURATION_PRESS,
            focus=motion.DURATION_HOVER,
            check=motion.DURATION_STATE,
        )
        # Icon swap: 1 -> the outgoing glyph is fully present, 0 -> the
        # incoming one has resolved. Symmetric, so it reads the same
        # whichever way the state went.
        self._outgoing_icon: str | None = None
        self._swap = ValueAnimator(self, 0.0, motion.ICON_SWAP,
                                   motion.EASE_IN_OUT, spatial=False)
        self.toggled.connect(
            lambda on: self._anim.to("check", 1.0 if on else 0.0, exiting=not on)
        )

    # --------------------------------------------------------------- api

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        self._icon_role = _ICON_ROLE_FOR_VARIANT.get(variant, "default")
        t.set_variant(self, "variant", variant)
        self.update()

    def set_icon(self, name: str | None, role: str | None = None) -> None:
        if name != self._icon_name and self._icon_name and name:
            self._outgoing_icon = self._icon_name
            self._swap.set_now(1.0)
            self._swap.to(0.0)
        self._icon_name = name
        if role:
            self._icon_role = role
        self.updateGeometry()
        self.update()

    def set_square(self, square: bool) -> None:
        """Icon-only: a square target with no label padding."""
        self._square = square
        t.set_variant(self, "shape", "icon" if square else None)
        self.updateGeometry()
        self.update()

    def refresh_icon(self) -> None:
        """Icons are tinted at paint time, so a theme change only needs a
        repaint here. Kept as a method so the theme sweep can call it
        uniformly across widget types."""
        self.update()

    # ---------------------------------------------------------- geometry

    def _icon_size(self) -> int:
        return _ICON_SIZE_FOR_SIZE.get(self._size, t.ICON_MD)

    def sizeHint(self) -> QSize:  # noqa: N802
        height = _HEIGHT_FOR_SIZE.get(self._size, t.CONTROL_MD)
        if self._square:
            return QSize(height, height)
        pad = _PAD_FOR_SIZE.get(self._size, t.SPACE_XL)
        width = pad * 2
        if self.text():
            width += QFontMetrics(self.font()).horizontalAdvance(self.text())
        if self._icon_name:
            width += self._icon_size() + (t.SPACE_MD if self.text() else 0)
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    # ------------------------------------------------------------ events

    def enterEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled():
            self._anim.to("hover", 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._anim.to("hover", 0.0, exiting=True)
        self._anim.to("press", 0.0, exiting=True)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled():
            self._anim.to("press", 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._anim.to("press", 0.0, exiting=True)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._anim.to("press", 1.0)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        self._anim.to("press", 0.0, exiting=True)
        super().keyReleaseEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        # Only keyboard focus draws a ring; a ring on every mouse click is
        # noise. See components/focus.py.
        if event.reason() in (
            Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason, Qt.FocusReason.MenuBarFocusReason,
        ):
            self._anim.to("focus", 1.0)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._anim.to("focus", 0.0, exiting=True)
        super().focusOutEvent(event)

    # ------------------------------------------------------------- paint

    def _surface(self) -> tuple[QColor, QColor, QColor, str]:
        """(top fill, bottom fill, border, text role) for this variant in
        its current animated state."""
        hover = self._anim["hover"]
        press = self._anim["press"]
        check = self._anim["check"]
        p = t.theme_manager.palette
        clear = QColor(0, 0, 0, 0)

        if not self.isEnabled():
            if self._variant in (VARIANT_PRIMARY, VARIANT_DANGER):
                base = QColor(p.surface_active)
                return base, base, QColor(p.border), "text_disabled"
            if self._variant in (VARIANT_LINK, VARIANT_SUBTLE):
                # A disabled link is still text, not an empty box.
                return clear, clear, clear, "text_disabled"
            return clear, clear, QColor(p.border), "text_disabled"

        if self._variant == VARIANT_PRIMARY:
            fill = blend(p.accent_solid, p.accent_solid_hover, hover)
            fill = blend(fill, QColor(p.accent_solid_pressed), press)
            top = blend(fill, QColor(255, 255, 255), 0.10)
            return top, fill, QColor(fill).darker(120), "text_on_accent"

        if self._variant == VARIANT_DANGER:
            fill = blend(p.danger_strong, p.danger_fg, hover)
            fill = blend(fill, QColor(p.danger_strong).darker(115), press)
            top = blend(fill, QColor(255, 255, 255), 0.10)
            return top, fill, QColor(fill).darker(120), "text_on_accent"

        if self._variant == VARIANT_LINK:
            return clear, clear, clear, "accent_fg"

        if self._variant == VARIANT_DANGER_QUIET:
            fill = blend(clear, QColor(p.danger_bg), max(hover, press))
            border = blend(p.border_strong, p.danger_fg, hover)
            return fill, fill, border, "danger_fg"

        if self._variant == VARIANT_SUBTLE:
            fill = blend(clear, QColor(p.surface_hover), hover)
            fill = blend(fill, QColor(p.surface_active), press)
            if check:
                fill = blend(fill, QColor(p.accent_subtle), check)
            border = blend(clear, QColor(p.accent), check)
            if check > 0.5:
                role = "accent_fg"
            else:
                role = "text_primary" if hover > 0.4 else "text_secondary"
            return fill, fill, border, role

        # secondary: a real raised surface, lit from the top
        top = blend(p.surface, p.surface_hover, hover)
        top = blend(top, QColor(p.surface_active), press)
        bottom = blend(top, QColor(p.canvas), 0.35 if p.is_dark else 0.10)
        return top, bottom, QColor(p.border_strong), "text_primary"

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        scale = lerp(1.0, _PRESS_SCALE, self._anim["press"])
        center = QRectF(self.rect()).center()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.translate(-center)

        radius = t.RADIUS_MD if self._size == "lg" else t.RADIUS_SM
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        top, bottom, border, text_role = self._surface()
        palette = t.theme_manager.palette

        if top.alpha() or bottom.alpha():
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gradient.setColorAt(0.0, top)
            gradient.setColorAt(1.0, bottom)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, radius, radius)

        if border.alpha():
            painter.setPen(QPen(border, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

        # 1px of light along the upper edge, clipped to the rounded shape.
        # This is the difference between a filled rectangle and a surface.
        if top.alpha() > 120:
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            painter.save()
            painter.setClipPath(path)
            strong = self._variant in (VARIANT_PRIMARY, VARIANT_DANGER)
            painter.setPen(QPen(
                QColor(palette.highlight_strong if strong else palette.highlight), 1
            ))
            painter.drawLine(
                QRectF(rect).left() + radius * 0.7, rect.top() + 0.75,
                QRectF(rect).right() - radius * 0.7, rect.top() + 0.75,
            )
            painter.restore()

        self._paint_focus_ring(painter, rect, radius)
        self._paint_content(painter, text_role)
        painter.end()

    def _paint_focus_ring(self, painter: QPainter, rect: QRectF, radius: float) -> None:
        focus = self._anim["focus"]
        if focus <= 0.01:
            return
        ring = QColor(t.theme_manager.palette.focus_ring)
        ring.setAlphaF(min(1.0, focus))
        painter.setPen(QPen(ring, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            rect.adjusted(-2.5, -2.5, 2.5, 2.5), radius + 2.5, radius + 2.5
        )

    def _icon_tint(self, text_color: QColor) -> QColor:
        palette = t.theme_manager.palette
        if not self.isEnabled():
            return QColor(palette.text_disabled)
        role = _ROLE_COLOR.get(self._icon_role)
        if role and self._icon_role not in ("accent",):
            return QColor(palette.color(role))
        if self._variant == VARIANT_SUBTLE and not self.isChecked():
            # Icons brighten with their label as the pointer arrives.
            return blend(palette.text_secondary, palette.text_primary,
                         self._anim["hover"])
        return text_color

    def _draw_swapping_icon(self, painter: QPainter, x: float, top: int,
                            size: int, tint: QColor, swap: float) -> None:
        """Cross-fade two glyphs in one slot, through blur and scale.

        The blur is what makes this read as one object changing rather
        than two objects passing each other; it comes from a cached
        pre-blurred pixmap, so it costs nothing per frame.
        """
        from app.ui.svg_icon import blurred_pixmap, tinted_pixmap

        centre_x = x + size / 2
        centre_y = top + size / 2

        # Outgoing: shrinks toward SCALE_ICON_SWAP and blurs out.
        painter.save()
        painter.setOpacity(swap)
        scale = motion.lerp(motion.SCALE_ICON_SWAP, 1.0, swap)
        painter.translate(centre_x, centre_y)
        painter.scale(scale, scale)
        painter.translate(-centre_x, -centre_y)
        blur = max(0, round(motion.BLUR_SMALL * (1.0 - swap)))
        painter.drawPixmap(
            int(round(x)), top,
            blurred_pixmap(self._outgoing_icon, size, tint.name(), blur),
        )
        painter.restore()

        # Incoming: grows in from the same scale as the outgoing leaves.
        painter.save()
        painter.setOpacity(1.0 - swap)
        scale = motion.lerp(1.0, motion.SCALE_ICON_SWAP, swap)
        painter.translate(centre_x, centre_y)
        painter.scale(scale, scale)
        painter.translate(-centre_x, -centre_y)
        painter.drawPixmap(
            int(round(x)), top,
            blurred_pixmap(self._icon_name, size, tint.name(),
                           max(0, round(motion.BLUR_SMALL * swap))),
        )
        painter.restore()

    def _paint_content(self, painter: QPainter, text_role: str) -> None:
        from app.ui.svg_icon import tinted_pixmap

        palette = t.theme_manager.palette
        color = QColor(palette.color(text_role))
        text = self.text()
        icon_size = self._icon_size()
        has_icon = bool(self._icon_name)
        gap = t.SPACE_MD if (has_icon and text) else 0

        metrics = QFontMetrics(self.font())
        text_width = metrics.horizontalAdvance(text) if text else 0
        content = text_width + (icon_size if has_icon else 0) + gap
        rect = QRectF(self.rect())
        x = rect.center().x() - content / 2

        if has_icon:
            tint = self._icon_tint(color)
            top = int(round(rect.center().y() - icon_size / 2))
            swap = self._swap.value
            if swap > 0.02 and self._outgoing_icon:
                self._draw_swapping_icon(
                    painter, x, top, icon_size, tint, swap,
                )
            else:
                painter.drawPixmap(
                    int(round(x)), top,
                    tinted_pixmap(self._icon_name, icon_size, tint.name()),
                )
            x += icon_size + gap

        if text:
            painter.setPen(color)
            painter.setFont(self.font())
            painter.drawText(
                QRectF(x, rect.top(), text_width + 2, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )


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
    """A square, label-less action. Always carries a tooltip: an icon with
    no accessible name is a puzzle, not a control."""

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
        self.set_square(True)
        self.setCheckable(checkable)
        self.setAccessibleName(tooltip)


class AccentButton(Button):
    """The product's primary action.

    Kept as its own class rather than folded into `Button` because "this
    is *the* action on this surface" is a design statement worth naming,
    and because the compose/send/save call sites read better for it.
    """

    def __init__(self, text: str = "", parent=None, **kwargs):
        kwargs.setdefault("variant", VARIANT_PRIMARY)
        kwargs.setdefault("size", "lg")
        super().__init__(text, parent=parent, **kwargs)


class ToolIconButton(QToolButton):
    """A QToolButton for the few places Qt wants one (a menu popup with an
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
        from app.ui.svg_icon import themed

        size = _ICON_SIZE_FOR_SIZE.get(self._size, t.ICON_MD)
        self.setIcon(themed(self._icon_name, size, "default"))
        self.setIconSize(QSize(size, size))


def refresh_button_icons(root) -> None:
    """Repaint every themed icon under `root` after a theme change.

    Painted buttons re-tint themselves on their next repaint; anything
    still holding a cached QIcon rebuilds it. Walking the tree once per
    switch is cheaper than every widget subscribing to a signal.
    """
    for widget in root.findChildren(object):
        refresh = getattr(widget, "refresh_icon", None)
        if callable(refresh):
            refresh()

"""The small set of reusable controls every screen is built from.

WHY THIS FILE EXISTS. Buttons were being made three different ways: a bare
QPushButton here, a QPushButton with objectName="iconButton" there, an
AccentButton somewhere else, and a QPushButton wearing the compose
button's object name inside the empty state. Four vocabularies for one
control, and the fourth one meant the "Add account" button in the empty
state was styled as the app's primary compose action by accident.

So: ONE Button with named variants, ONE IconButton, ONE Badge. Screens
choose a variant; they do not choose a stylesheet. Adding a fifth kind of
button now means adding a variant here, where every screen sees it, rather
than another object name that only one file knows about.

Deliberately small. Six primitives, not thirty: a component that exists
once is not a system, it is a widget with extra steps.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import (
    Property,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QTextLayout
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui import motion, theme as t
from app.ui.svg_icon import icon_set, simple_icon


class Variant(str, Enum):
    """How loud a button is allowed to be.

    ONE PRIMARY PER SCREEN. That is the whole rule, and it is why these are
    named by role rather than by color: a screen with two filled buttons
    has not decided what it wants the user to do.
    """

    PRIMARY = "primary"        # the one filled control on a screen
    SECONDARY = "secondary"    # bordered, quiet until hovered
    GHOST = "ghost"            # no border at all; toolbars, inline actions
    DESTRUCTIVE = "destructive"  # deletes data, and says so in the error hue


class Button(QPushButton):
    """The app's button.

    Sets an objectName the stylesheet keys off, so all state handling
    (hover, pressed, focus, disabled) lives in one QSS block per variant
    instead of being re-derived per call site.

    THE PRIMARY VARIANT PAINTS ITS OWN FILL, and it is worth saying why a
    component with a perfectly good QSS block reaches for a QPainter.
    Qt Style Sheets cannot tween: `:pressed` swaps the colour on the frame
    the mouse went down and swaps it back on the frame it came up, which
    at 60fps is a flicker rather than a press. The fill is therefore
    animated here across DURATION_FAST, so the button dips under the
    pointer and recovers.

    This used to live in a separate AccentButton class, which meant the
    app had one button that felt alive and three that did not, depending
    on which of the two vocabularies a screen happened to use. Folding it
    in is the point: a button in one part of the product should feel like
    a button in another.

    Only PRIMARY gets the painted fill. A secondary or ghost button has no
    fill at rest, so there is nothing to dip - their feedback is the QSS
    hover surface, which is correct for a control that is meant to stay
    quiet.
    """

    def __init__(self, text: str = "", variant: Variant = Variant.SECONDARY,
                 icon: str = "", parent=None):
        super().__init__(text, parent)
        self._variant = Variant(variant)
        self._icon_name = ""
        self.setObjectName(f"btn-{self._variant.value}")
        self.setFont(t.make_font("button"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(t.HEIGHT_MD)
        # Buttons should not stretch to fill a layout: a 700px-wide "Save"
        # is a banner, not a control.
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self._press = 0.0
        self._hover = 0.0
        if icon:
            self.set_icon(icon)

    # -- animated state ---------------------------------------------------

    def _get_press(self) -> float:
        return self._press

    def _set_press(self, value: float) -> None:
        self._press = value
        self.update()

    pressProgress = Property(float, _get_press, _set_press)

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hoverProgress = Property(float, _get_hover, _set_hover)

    def _animate(self, prop: str, end: float) -> None:
        # Through motion, so the reduced-motion setting reaches these too -
        # a button that still tweens when every other transition has been
        # turned off is the one thing the setting was asked to stop.
        if not motion.motion_enabled():
            self.setProperty(prop, end)
            self.update()
            return
        anim = QPropertyAnimation(self, prop.encode(), self)
        anim.setDuration(t.DURATION_FAST)
        anim.setEasingCurve(motion.curve())
        anim.setStartValue(float(self.property(prop)))
        anim.setEndValue(end)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def enterEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled():
            self._animate("hoverProgress", 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate("hoverProgress", 0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled():
            self._animate("pressProgress", 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._animate("pressProgress", 0.0)
        super().mouseReleaseEvent(event)

    # -- paint ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._variant is not Variant.PRIMARY:
            return super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # FLAT, NOT A GRADIENT. The accent is a luminance value, so hover
        # moves it one step up the warm ramp and press one step down. A
        # two-stop vertical gradient here would be a lit-plastic button,
        # which is the single most reliable tell of a generic dark theme.
        if self.isEnabled():
            fill = QColor(t.mix(t.ACCENT, t.ACCENT_HOVER, self._hover))
            fill = QColor(t.mix(fill.name(), t.ACCENT_PRESSED, self._press))
            border = fill
        else:
            fill = QColor(t.BG_SELECTED)
            border = QColor(t.BORDER)

        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(rect, t.RADIUS_SM, t.RADIUS_SM)
        painter.end()

        # Qt still lays out and draws the label, icon and focus rect, so
        # this stays a real QPushButton rather than a bespoke widget that
        # has to reimplement all of that.
        super().paintEvent(event)

    # -- content ----------------------------------------------------------

    def set_icon(self, name: str) -> None:
        """Tint follows the variant, because a primary button's label sits
        on the emphasis fill and everything else sits on a surface."""
        self._icon_name = name
        color = {
            Variant.PRIMARY: t.TEXT_ON_ACCENT,
            Variant.DESTRUCTIVE: t.DESTRUCTIVE,
        }.get(self._variant, t.ICON_SECONDARY)
        self.setIcon(simple_icon(name, t.ICON_SIZE_ACTION, color))
        self.setIconSize(QSize(t.ICON_SIZE_ACTION, t.ICON_SIZE_ACTION))

    def retheme(self) -> None:
        if self._icon_name:
            self.set_icon(self._icon_name)

    def variant(self) -> Variant:
        return self._variant


class IconButton(QPushButton):
    """A square, label-less action.

    Native desktop clients use icon-only for secondary toolbar actions and
    keep words for the primary one; icon+text on every control reads as a
    web toolbar. The tooltip is mandatory rather than optional, because an
    icon-only control with no tooltip is a guess.
    """

    def __init__(self, icon_name: str, tooltip: str, *, checkable: bool = False,
                 size: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("btn-icon")
        self.setToolTip(tooltip)
        # The accessible name is what a screen reader announces; without it
        # this control is called "" out loud.
        self.setAccessibleName(tooltip)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._px = size or t.ICON_SIZE_TOOLBAR
        self.setIconSize(QSize(self._px, self._px))
        self.set_icon(icon_name)
        self.setFixedSize(t.HEIGHT_MD, t.HEIGHT_MD)

    def set_icon(self, icon_name: str, *, colour: str | None = None) -> None:
        """Change (or re-tint) the glyph.

        Needed for two separate reasons, and it is worth naming both:

          * A BUTTON WHOSE ICON IS ITS STATE. The star toggles between an
            outline and a filled glyph, and the filled one is the one place
            in the reading pane hue is spent.
          * A THEME SWITCH. An icon is a pixmap tinted at build time, so
            unlike text it cannot follow the stylesheet - every widget
            holding one has to rebuild it. See theme.retheme_tree.

        `colour` overrides the normal tint only; hover, checked and
        disabled keep coming from the icon-mode ramp, so a coloured icon
        still greys out correctly when its button is disabled.
        """
        self._icon_name = icon_name
        self.setIcon(icon_set(
            icon_name, self._px,
            normal=colour or t.ICON_SECONDARY,
            active=colour or t.ICON_ACTIVE,
            selected=colour or t.ICON_SELECTED,
            disabled=t.ICON_DISABLED,
        ))

    def retheme(self) -> None:
        self.set_icon(self._icon_name)


class Badge(QLabel):
    """A count, or a dot.

    Counts are set in the mono face and on a neutral surface, NOT filled
    with the accent: an unread count is information, and one bright chip
    per account would be four bright chips in a four-account sidebar, all
    competing with the one primary action on the screen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("badge")
        self.setFont(t.make_font("badge"))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setVisible(False)

    def set_count(self, count: int) -> None:
        # 99+ rather than a four-digit badge that resizes the row it is in.
        self.setText(str(count) if count < 100 else "99+")
        self.setVisible(count > 0)


class Rule(QFrame):
    """A one-pixel hairline. Horizontal by default.

    Separation in this app is a line or a change of surface, never a
    shadow and never a rounded box drawn around a group.
    """

    def __init__(self, vertical: bool = False, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        if vertical:
            self.setFixedWidth(1)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setFixedHeight(1)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setObjectName("rule")


class Field(QWidget):
    """A labelled control: caption above, control below, hint underneath.

    Every form in the app used its own arrangement of QLabel and QLineEdit
    with its own spacing. This is the one arrangement, so Settings, Compose
    and Add Account stop looking like three products.
    """

    def __init__(self, label: str, control: QWidget, hint: str = "", parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(t.SPACE_XS + 2)

        self._label = QLabel(label)
        self._label.setFont(t.make_font("field_label"))
        t.role(self._label, "secondary")
        # Clicking the caption focuses the control, and screen readers read
        # the two as one thing.
        self._label.setBuddy(control)
        col.addWidget(self._label)

        self.control = control
        col.addWidget(control)

        self._hint = QLabel(hint)
        self._hint.setFont(t.make_font("caption"))
        t.role(self._hint, "tertiary")
        self._hint.setWordWrap(True)
        self._hint.setVisible(bool(hint))
        col.addWidget(self._hint)

    def set_hint(self, text: str, *, error: bool = False) -> None:
        """The hint doubles as the field's error line.

        A field that explains its own problem in place is better than a
        modal that explains it somewhere else, and it is why validation
        here never opens a dialog.
        """
        self._hint.setText(text)
        self._hint.setStyleSheet(
            f"color: {t.DESTRUCTIVE if error else t.TEXT_TERTIARY};"
        )
        self._hint.setVisible(bool(text))
        self.control.setProperty("invalid", "true" if error else "")
        # Qt does not re-evaluate a property selector until the style is
        # re-polished on that widget.
        self.control.style().unpolish(self.control)
        self.control.style().polish(self.control)


class Toolbar(QWidget):
    """A horizontal band of controls with a hairline under it.

    Not QToolBar: QToolBar brings a drag handle, an extension chevron, a
    right-click menu that can hide the band, and its own layout rules, all
    of which had to be styled away. This is the band, and nothing else.

    `manual=True` leaves out the row layout, for a band that places its
    children itself (the main toolbar centres the dock, which no box
    layout can do). A layout left in place but empty would still own the
    band's minimum size and let the window shrink past its contents.
    """

    def __init__(self, parent=None, *, manual: bool = False):
        super().__init__(parent)
        self.setObjectName("toolbarBand")
        self.setFixedHeight(t.TOOLBAR_HEIGHT)
        self.row = None
        if not manual:
            self.row = QHBoxLayout(self)
            self.row.setContentsMargins(t.SPACE_LG, 0, t.SPACE_LG, 0)
            self.row.setSpacing(t.SPACE_SM)


class ElidingLabel(QLabel):
    """A single-line label that shortens itself instead of overflowing.

    WHY THIS HAD TO EXIST. A plain QLabel given more text than it has room
    for does not elide - it reports a wider sizeHint and pushes on its
    layout, or is simply clipped by whatever is next to it. The reading
    pane's sender line was the case that found it: a 59-character display
    name ran under the timestamp beside it, and at a narrower pane width
    the two collided outright.

    Word wrap is the other answer and it is the wrong one HERE. A name is
    one thing; letting it take three lines pushes the subject, the actions
    and the message itself down the page, so the layout of the whole
    reading pane would depend on how long somebody's name is.

    Keeps the full text in the tooltip, because eliding is a display
    decision and the reader may still need the whole thing.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full = text
        # Without this the label still reports its untruncated width as a
        # minimum, and the layout grows to fit rather than letting it
        # elide - the elision would then never actually happen.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setTextFormat(Qt.TextFormat.PlainText)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming convention)
        self._full = text or ""
        self.setToolTip("")
        super().setText(self._full)
        self._relayout()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        if not self._full:
            return
        metrics = self.fontMetrics()
        available = max(0, self.width())
        if available <= 0 or metrics.horizontalAdvance(self._full) <= available:
            if super().text() != self._full:
                super().setText(self._full)
            self.setToolTip("")
            return
        super().setText(
            metrics.elidedText(self._full, Qt.TextElideMode.ElideRight, available)
        )
        # Elided text is a display decision; the reader may still need the
        # whole name, so it stays reachable rather than being lost.
        self.setToolTip(self._full)


class ClampedLabel(QLabel):
    """A wrapping label that stops after a set number of lines.

    WHY A THIRD LABEL TYPE. The reading pane's title is the one element
    allowed to wrap, and at a narrow pane width a real subject took SEVEN
    lines - pushing the attribution, the action row and the message itself
    so far down that the header became the page. Eliding it to one line
    (ElidingLabel) is wrong for a title, because a subject genuinely needs
    more than one line to be read. What it needs is a ceiling.

    Qt has no multi-line elision, so the text is laid out with QTextLayout
    to find where the last permitted line ends, cut there, and given an
    ellipsis that fits. The full text stays in the tooltip.

    A HEIGHT CEILING ALONE WOULD NOT DO. Capping maximumHeight clips the
    overflowing line halfway through its x-height, which reads as a
    rendering fault rather than as a truncation - the ellipsis is what
    makes it legible as a decision.
    """

    def __init__(self, text: str = "", max_lines: int = 3, parent=None):
        super().__init__(text, parent)
        self._full = text
        self._max_lines = max(1, int(max_lines))
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming convention)
        self._full = text or ""
        super().setText(self._full)
        self._clamp()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._clamp()

    def _line_breaks(self, width: int):
        """Where each wrapped line starts and ends, at this width."""
        layout = QTextLayout(self._full, self.font())
        layout.beginLayout()
        lines = []
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            lines.append((line.textStart(), line.textLength()))
        layout.endLayout()
        return lines

    def _clamp(self) -> None:
        width = self.width()
        if not self._full or width <= 0:
            return

        lines = self._line_breaks(width)
        if len(lines) <= self._max_lines:
            if super().text() != self._full:
                super().setText(self._full)
            self.setToolTip("")
            return

        start, length = lines[self._max_lines - 1]
        cut = start + length
        kept = self._full[:cut].rstrip()
        # Trim the final line back until the ellipsis fits on it, so the
        # last thing the reader sees is "..." and not a word cut in half.
        metrics = self.fontMetrics()
        while kept and metrics.horizontalAdvance(kept[start:] + "…") > width:
            kept = kept[:-1]
        super().setText(kept.rstrip() + "…")
        self.setToolTip(self._full)


# ---------------------------------------------------------------- edges

# How far the softening reaches. Short enough that it never eats a whole
# row - it is a boundary treatment, not a vignette.
EDGE_FADE = 28


def paint_edge_fade(painter, rect, colour, *, top: bool = False,
                    bottom: bool = False, height: int = EDGE_FADE) -> None:
    """Soften where scrolling content meets the chrome.

    ADAPTED FROM MAGIC UI'S ProgressiveBlur. That component stacks eight
    backdrop-blur layers behind gradient masks so content dissolves into
    the edge instead of being cut by it. The blur is not the idea - the
    SOFT BOUNDARY is. What the eye reads is "this continues past here",
    where a hard edge reads as "this was chopped".

    Qt gets the same impression for almost nothing: a vertical gradient
    from the surface colour to fully transparent, painted OVER the
    content at the boundary. No blur, no backdrop sampling, no extra
    layers - one gradient fill per edge per paint, and only on the few
    pixels the fade covers.

    The colour must be the surface the content scrolls UNDER, or the fade
    resolves to the wrong shade and reads as a smudge. Both themes work
    because it is handed a token rather than a fixed value.
    """
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QLinearGradient

    solid = QColor(colour)
    clear = QColor(colour)
    clear.setAlpha(0)

    if top:
        band = QRectF(rect.left(), rect.top(), rect.width(), height)
        grad = QLinearGradient(band.topLeft(), band.bottomLeft())
        grad.setColorAt(0.0, solid)
        grad.setColorAt(1.0, clear)
        painter.fillRect(band, grad)

    if bottom:
        band = QRectF(
            rect.left(), rect.bottom() - height + 1, rect.width(), height
        )
        grad = QLinearGradient(band.bottomLeft(), band.topLeft())
        grad.setColorAt(0.0, solid)
        grad.setColorAt(1.0, clear)
        painter.fillRect(band, grad)

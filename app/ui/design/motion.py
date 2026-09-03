"""The motion language.

Qt Style Sheets have no `transition`. That single fact is why the app
looked dead: every hover, press, check and selection in a QSS-styled Qt
interface is an instant swap, and instant swaps read as "nothing is
happening" no matter how good the colors are.

The scale below is the **transitions.dev** token set (transitions.dev,
Jakub Antalik) ported to Qt, rather than numbers invented here. Its values
are tuned against real, shipped implementations of exactly the surfaces
this app has - dropdowns, modals, toasts, sliding tab indicators, skeleton
reveals, icon swaps - so the app inherits a coherent, already-argued motion
system instead of a pile of local guesses. Where Qt cannot express a CSS
property directly (`filter: blur`), the port says so and names what it
does instead.

Layered on top, from Apple's *Designing Fluid Interfaces*:

* **Respond on press, not on release.** Feedback starts the instant the
  pointer goes down.
* **Animate from the presentation value, never the target.** Every
  animator here restarts from wherever the value currently *is*, so an
  interaction interrupted mid-flight is picked up rather than snapped.
* **Exits are faster and quieter than entrances,** except where the
  motion is symmetric by nature (a sliding indicator, a page slide, an
  icon swap - the same journey in both directions).
* **Reduced motion collapses every duration to zero** through
  `theme_manager.duration()`, so state still changes, it just does not
  travel.

`StateAnimator` is the workhorse: a widget declares the interaction
channels it cares about ("hover", "press", "focus"), sets a target of 0 or
1 when its state changes, and paints with the interpolated value. It is
deliberately one small object rather than a QPropertyAnimation per state
per widget; the message list alone would otherwise carry hundreds.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPointF,
    QSequentialAnimationGroup,
    QVariantAnimation,
)
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage, QPixmap


def _bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1.0, 1.0))
    return curve


# --------------------------------------------------------------- easings
# The named curves, straight across from the token set.
EASE_SMOOTH_OUT = _bezier(0.22, 1.0, 0.36, 1.0)   # opens, closes, slides, resizes
EASE_IN_OUT = _bezier(0.42, 0.0, 0.58, 1.0)       # icon swap, text swap, reveals
EASE_OUT = _bezier(0.0, 0.0, 0.58, 1.0)           # tooltip in/out
EASE_BOUNCE = _bezier(0.34, 1.36, 0.64, 1.0)      # badge pop, entrance overshoot
EASE_BOUNCE_STRONG = _bezier(0.34, 3.85, 0.64, 1.0)  # hover-out settle
EASE_TOGGLE = _bezier(0.34, 1.35, 0.64, 1.0)      # switch thumb travel
EASE_DIGIT = _bezier(0.34, 1.45, 0.64, 1.0)       # number pop-in

# ------------------------------------------------------------- durations
DURATION_STAGGER = 40      # per-item stagger offset
DURATION_MICRO = 80        # intent delay, shake segment
DURATION_QUICK = 150       # modal/dropdown close, text swap
DURATION_FAST = 250        # icon swap, dropdown/modal open, tabs slide, page slide
DURATION_MEDIUM = 350      # panel close, toast open
DURATION_SLOW = 400        # panel open, skeleton reveal
DURATION_VERY_SLOW = 500   # emphasis: badge appear, text reveal

# Interaction feedback. Faster than any of the above, because these run on
# the input path: a press that takes 250ms to acknowledge feels broken.
DURATION_PRESS = 90
DURATION_HOVER = 130
DURATION_STATE = 190
DURATION_PANEL = DURATION_FAST
DURATION_EXIT = 0.7        # multiplier when a channel is unwinding

# ------------------------------------------------------------- distances
# The non-resting offset an element animates *from*, settling to 0.
DISTANCE_MICRO = 4         # text swap
DISTANCE_SMALL = 6         # error shake, small segment
DISTANCE_BASE = 8          # page slide, badge reveal, shake large segment
DISTANCE_MEDIUM = 12       # text reveal
DISTANCE_TOAST = 16        # toast rise
DISTANCE_LARGE = 30        # emphasis entrance

# ---------------------------------------------------------------- scales
SCALE_LARGE = 0.96         # modal open / close
SCALE_MEDIUM = 0.97        # dropdown open, toast
SCALE_SMALL = 0.98         # tooltip open
SCALE_TINY = 0.99          # dropdown close
SCALE_ICON_SWAP = 0.25     # the outgoing icon's end scale

# ------------------------------------------------------------------ blur
# Qt has no per-widget `filter: blur()` that is cheap enough to animate on
# a scrolling surface, so blur is used where it is affordable and honest:
# pre-blurred *pixmaps* for icon swaps (cached, so free after first use)
# and a QGraphicsBlurEffect on transient floating surfaces. Everywhere
# else the port drops the blur rather than faking it with opacity and
# pretending; the comment at each call site says which.
BLUR_SMALL = 2
BLUR_MEDIUM = 3
BLUR_LARGE = 8

# -------------------------------------------------------- per-transition
# Named after the transition they belong to, so a call site reads as the
# thing it is doing rather than as an arbitrary number.
TABS_DURATION = DURATION_FAST          # sliding indicator, symmetric
MODAL_OPEN, MODAL_CLOSE = DURATION_FAST, DURATION_QUICK
DROPDOWN_OPEN, DROPDOWN_CLOSE = DURATION_FAST, DURATION_QUICK
PANEL_OPEN, PANEL_CLOSE = DURATION_SLOW, DURATION_MEDIUM
PAGE_SLIDE = DURATION_FAST             # symmetric
ICON_SWAP = DURATION_FAST              # symmetric
TOAST_OPEN, TOAST_CLOSE = DURATION_MEDIUM, DURATION_FAST
ACCORDION = DURATION_FAST              # symmetric
CARD_RESIZE = 300
TEXT_SWAP = DURATION_QUICK             # symmetric
SKELETON_PULSE = 1000
SKELETON_REVEAL = DURATION_SLOW
SHIMMER_CYCLE = 2000
TOGGLE_TRAVEL = DURATION_MEDIUM
TOGGLE_OVERSHOOT = 1                   # px past the stop, then settle back
NUMBER_POP = DURATION_VERY_SLOW
SHAKE_LONG, SHAKE_SHORT = DURATION_MICRO, 60
STAGGER_STEP = DURATION_STAGGER
STAGGER_BUDGET = 300                   # total stagger never exceeds this
INTENT_DELAY = DURATION_MICRO          # filters accidental triggers


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def blend(color_a, color_b, t: float) -> QColor:
    """Interpolate two colors, alpha included."""
    a = QColor(color_a)
    b = QColor(color_b)
    t = max(0.0, min(1.0, t))
    return QColor(
        round(lerp(a.red(), b.red(), t)),
        round(lerp(a.green(), b.green(), t)),
        round(lerp(a.blue(), b.blue(), t)),
        round(lerp(a.alpha(), b.alpha(), t)),
    )


def with_alpha(color, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c


def stagger_delay(index: int, count: int, step: int = STAGGER_STEP) -> int:
    """Per-item entrance delay, with the total capped.

    A stagger that runs longer than the budget stops reading as rhythm and
    starts reading as the list being slow, so past the cap the step
    shrinks rather than the sequence growing.
    """
    if count <= 1:
        return 0
    if step * (count - 1) > STAGGER_BUDGET:
        step = max(8, STAGGER_BUDGET // (count - 1))
    return index * step


def blur_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
    """A blurred copy of a pixmap.

    Used for icon swaps, where the outgoing glyph blurs out as the
    incoming one resolves - the detail that makes a swap read as one
    object changing rather than two objects crossfading past each other.
    Rendered through Qt's own QGraphicsBlurEffect (the same Gaussian the
    scene graph uses) rather than a hand-rolled convolution, and the
    caller caches the result, so it costs one render per icon per theme.
    """
    if radius <= 0 or pixmap.isNull():
        return pixmap

    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import (
        QGraphicsBlurEffect,
        QGraphicsPixmapItem,
        QGraphicsScene,
    )

    # A margin, or the blur is clipped square at the pixmap's edges.
    margin = radius * 2
    size = pixmap.size() + QSize(margin * 2, margin * 2)

    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pixmap)
    item.setPos(margin, margin)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    item.setGraphicsEffect(effect)
    scene.addItem(item)

    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scene.render(
        painter, QRectF(image.rect()),
        QRectF(0, 0, size.width(), size.height()),
    )
    painter.end()
    scene.clear()
    return QPixmap.fromImage(
        image.copy(margin, margin, pixmap.width(), pixmap.height())
    )


class StateAnimator(QObject):
    """Interpolated 0..1 values for a widget's interaction states.

    Usage::

        self._anim = StateAnimator(self, hover=DURATION_HOVER,
                                   press=DURATION_PRESS)
        ...
        self._anim.to("hover", 1.0)          # on enterEvent
        t = self._anim["hover"]              # inside paintEvent

    Every channel repaints its widget as it runs, restarts from the value
    currently on screen (so an interrupted interaction is picked up rather
    than snapped), and honours the OS reduced-motion preference.
    """

    # Channels that only change colour or opacity in place. These survive
    # reduced motion (shortened), because nothing about them travels.
    NON_SPATIAL = frozenset({"hover", "focus", "check", "select", "fade"})

    def __init__(self, widget, **channels: int):
        super().__init__(widget)
        self._widget = widget
        self._values: dict[str, float] = {}
        self._durations: dict[str, int] = {}
        self._easings: dict[str, QEasingCurve] = {}
        self._animations: dict[str, QVariantAnimation] = {}
        for name, duration in channels.items():
            self._values[name] = 0.0
            self._durations[name] = duration

    def __getitem__(self, name: str) -> float:
        return self._values.get(name, 0.0)

    def value(self, name: str) -> float:
        return self._values.get(name, 0.0)

    def set_easing(self, name: str, curve: QEasingCurve) -> None:
        self._easings[name] = curve

    def set_now(self, name: str, value: float) -> None:
        """Jump straight to a value, with no animation."""
        animation = self._animations.pop(name, None)
        if animation is not None:
            animation.stop()
            animation.deleteLater()
        self._values[name] = value
        self._widget.update()

    def to(self, name: str, target: float, *, exiting: bool = False,
           duration: int | None = None) -> None:
        """Animate a channel toward `target` (0..1)."""
        from app.ui.design.theme import theme_manager

        current = self._values.get(name, 0.0)
        if abs(current - target) < 0.001:
            return
        base = duration or self._durations.get(name, DURATION_STATE)
        if exiting:
            base = int(base * DURATION_EXIT)
        ms = theme_manager.duration(base, spatial=name not in self.NON_SPATIAL)
        if ms <= 0:
            self.set_now(name, target)
            return

        animation = self._animations.get(name)
        if animation is None:
            animation = QVariantAnimation(self)
            animation.valueChanged.connect(
                lambda v, n=name: self._on_value(n, float(v))
            )
            self._animations[name] = animation
        animation.stop()
        animation.setEasingCurve(self._easings.get(name, EASE_SMOOTH_OUT))
        animation.setDuration(ms)
        animation.setStartValue(float(current))
        animation.setEndValue(float(target))
        animation.start()

    def _on_value(self, name: str, value: float) -> None:
        self._values[name] = value
        try:
            self._widget.update()
        except RuntimeError:  # widget torn down mid-animation
            pass


class ValueAnimator(QObject):
    """A single animated float that is not tied to an interaction state -
    a travelling indicator, a cross-fade, a shimmer phase."""

    def __init__(self, widget, value: float = 0.0,
                 duration: int = DURATION_STATE,
                 easing: QEasingCurve | None = None,
                 *, spatial: bool = True):
        super().__init__(widget)
        self._widget = widget
        self._value = value
        self._duration = duration
        # Whether this value moves something across the screen. A pure
        # cross-fade sets spatial=False and keeps working under reduced
        # motion; a travelling indicator does not.
        self._spatial = spatial
        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(easing or EASE_SMOOTH_OUT)
        self._animation.valueChanged.connect(self._on_value)

    @property
    def value(self) -> float:
        return self._value

    @property
    def running(self) -> bool:
        return self._animation.state() == QVariantAnimation.State.Running

    @property
    def target(self) -> float:
        """Where the value is heading - the same as `value` once it has
        arrived. Callers that need to decide something from the state
        being animated *towards*, rather than from the frame currently on
        screen, should ask this: mid-flight, `value` is a coordinate, not
        an answer."""
        if not self.running:
            return self._value
        return float(self._animation.endValue())

    def stop(self) -> None:
        self._animation.stop()

    def set_now(self, value: float) -> None:
        self._animation.stop()
        self._value = value
        self._widget.update()

    def to(self, target: float, *, duration: int | None = None,
           easing: QEasingCurve | None = None) -> None:
        from app.ui.design.theme import theme_manager

        if abs(self._value - target) < 0.001:
            return
        ms = theme_manager.duration(
            duration or self._duration, spatial=self._spatial
        )
        if ms <= 0:
            self.set_now(target)
            return
        self._animation.stop()
        if easing is not None:
            self._animation.setEasingCurve(easing)
        self._animation.setDuration(ms)
        # From the presentation value, not the target: an interrupted
        # animation continues from where the eye last saw it.
        self._animation.setStartValue(float(self._value))
        self._animation.setEndValue(float(target))
        self._animation.start()

    def _on_value(self, value) -> None:
        self._value = float(value)
        try:
            self._widget.update()
        except RuntimeError:
            pass


def shake(widget, on_offset, *, distance: int = DISTANCE_SMALL,
          overshoot: int = 4) -> QSequentialAnimationGroup | None:
    """The error shake: a per-segment left/right settle, not a wobble.

    `on_offset` is called with the current x offset in pixels; the caller
    decides whether that means moving a widget or shifting its paint. The
    segments shorten as they settle (80ms, 60ms, 60ms, 60ms), which is
    what makes it read as an object being knocked rather than vibrating.
    """
    from app.ui.design.theme import theme_manager

    if theme_manager.duration(SHAKE_LONG) <= 0:
        on_offset(0)
        return None

    steps = (
        (-distance, SHAKE_LONG),
        (overshoot, SHAKE_SHORT),
        (-overshoot + 2, SHAKE_SHORT),
        (0, SHAKE_SHORT),
    )
    group = QSequentialAnimationGroup(widget)
    previous = 0.0
    for target, duration in steps:
        animation = QVariantAnimation(group)
        animation.setDuration(duration)
        animation.setEasingCurve(EASE_SMOOTH_OUT)
        animation.setStartValue(float(previous))
        animation.setEndValue(float(target))
        animation.valueChanged.connect(lambda v: on_offset(float(v)))
        group.addAnimation(animation)
        previous = target
    group.start(QSequentialAnimationGroup.DeletionPolicy.DeleteWhenStopped)
    return group


def fade_in(widget, *, duration: int = DURATION_PANEL,
            start: float = 0.0) -> QVariantAnimation | None:
    """Fade a top-level widget in. A pure opacity change, so it survives
    reduced motion in shortened form."""
    from app.ui.design.theme import theme_manager

    ms = theme_manager.duration(duration, spatial=False)
    if ms <= 0:
        widget.setWindowOpacity(1.0)
        return None
    animation = QVariantAnimation(widget)
    animation.setDuration(ms)
    animation.setEasingCurve(EASE_SMOOTH_OUT)
    animation.setStartValue(start)
    animation.setEndValue(1.0)
    animation.valueChanged.connect(lambda v: widget.setWindowOpacity(float(v)))
    widget.setWindowOpacity(start)
    animation.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    return animation

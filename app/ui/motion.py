"""The app's motion vocabulary.

WHY THIS FILE EXISTS. Animation was being written per widget: the old nav
pill owned a QPropertyAnimation on a float, AccentButton owned another,
ToastHost a third, and each one picked its own duration and curve at the call site.
Three components, three slightly different ideas of what "fast" means. A
fourth would have made four. The durations and the curve already live in
theme.py; what was missing was one place that KNOWS HOW TO APPLY them, so
a component asks for "fade this in" rather than assembling an animation.

WHAT MOTION IS FOR HERE, AND WHAT IT IS NOT FOR

PRODUCT.md is explicit: "Nothing pulses, glows, or moves without a reason
a user could name." Every helper below is attached to a state change a
user caused - a selection moved, a panel opened, a send succeeded. None of
them loops, none of them idles, and none of them plays on first paint just
to make the app look alive. An app that animates while nothing is
happening is asking to be watched, and this one is trying to be read.

    fade_in / fade_out      a thing arrived or left
    cross_fade              one thing replaced another in place
    animate_property        a value moved (a width, an indicator, a float)
    flash                   an action landed and had no other visible result
    reveal                  content arrived because the context changed
    reveal_theme_change     the palette changed, spreading from its cause

THE REDUCED-MOTION RULE IS ENFORCED HERE, ONCE. Qt exposes no
prefers-reduced-motion, so the switch is the app's own setting. Every
helper checks `motion_enabled()` and, when motion is off, jumps straight
to the END STATE rather than skipping the change - a disabled animation
must still leave the widget looking correct, which is the bug that makes
most reduced-motion implementations worse than none.

PERFORMANCE. Qt animates on the UI thread, so an animation running while a
10,000-row list scrolls costs frames the list needed. Hence: durations from
theme.py only (120/180/280ms, all short), one opacity effect per widget
reused rather than one per call, and NO animation on anything painted
per-row by a delegate. The email list's hover and selection feedback is
deliberately not tweened for exactly this reason - it repaints per row per
frame, and a tween there would be the one animation in the app you could
feel.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QByteArray,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import QBrush, QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from app.ui import theme as t

# Flipped once the app knows its settings (MainWindow._apply_motion_pref).
# Module-level rather than threaded through every call, because otherwise
# every widget that wanted to fade would need a reference to Settings.
_ENABLED = True


def set_motion_enabled(enabled: bool) -> None:
    global _ENABLED
    _ENABLED = bool(enabled)


def motion_enabled() -> bool:
    return _ENABLED


def curve() -> QEasingCurve:
    """The app's single easing curve, as an object.

    Two components easing differently is the kind of difference nobody can
    name and everybody notices.
    """
    return QEasingCurve(t.ease_out())


def _opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    """One effect per widget, reused.

    A fresh QGraphicsOpacityEffect per animation attaches another QObject
    to the widget every time it fades, and Qt keeps all of them alive for
    the widget's lifetime.
    """
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    return effect


def animate_property(target, prop: str, end, *, start=None,
                     duration: int | None = None, on_done=None):
    """Tween one Qt property, honouring the reduced-motion setting.

    Returns the running animation, or None when motion is off - in which
    case the property is set to `end` immediately, so no caller has to
    write the no-motion branch itself.
    """
    if not _ENABLED:
        target.setProperty(prop, end)
        if on_done is not None:
            on_done()
        return None

    anim = QPropertyAnimation(target, QByteArray(prop.encode()), target)
    anim.setDuration(t.DURATION_BASE if duration is None else duration)
    anim.setEasingCurve(curve())
    anim.setStartValue(target.property(prop) if start is None else start)
    anim.setEndValue(end)
    if on_done is not None:
        anim.finished.connect(on_done)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def set_opacity(widget: QWidget, value: float) -> None:
    """Hold a widget at an opacity, through the same reused effect the
    fades use - for content that will fade in a beat after its window."""
    _opacity_effect(widget).setOpacity(float(value))


def fade_in(widget: QWidget, *, duration: int | None = None, on_done=None):
    """Show a widget by fading it up from transparent.

    setVisible FIRST, then animate. A widget that is still hidden when the
    animation starts contributes no size to its layout, so the layout jumps
    as it appears and the opacity tween then plays over the settled
    position. Showing first makes the geometry final before anything moves,
    which is the difference between a fade and a flinch.
    """
    widget.setVisible(True)
    if not _ENABLED:
        _opacity_effect(widget).setOpacity(1.0)
        if on_done is not None:
            on_done()
        return None

    effect = _opacity_effect(widget)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(t.DURATION_BASE if duration is None else duration)
    anim.setEasingCurve(curve())
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    if on_done is not None:
        anim.finished.connect(on_done)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def fade_out(widget: QWidget, *, duration: int | None = None,
             hide: bool = True, on_done=None):
    """Fade a widget down, then optionally hide it.

    EXIT IS FASTER THAN ENTRY. Something arriving is information the user
    still has to take in; something leaving has already been read, and
    making them wait for it is how motion turns into latency.
    """
    if duration is None:
        duration = t.DURATION_FAST

    def finish() -> None:
        if hide:
            widget.setVisible(False)
        if on_done is not None:
            on_done()

    if not _ENABLED:
        finish()
        return None

    effect = _opacity_effect(widget)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setEasingCurve(curve())
    anim.setStartValue(effect.opacity())
    anim.setEndValue(0.0)
    anim.finished.connect(finish)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def cross_fade(widget: QWidget, swap, *, duration: int | None = None):
    """Replace a widget's contents without the change flickering.

    `swap` runs at the darkest point, so the old content is never seen
    turning into the new one. This is what the reading pane uses: choosing
    a different message should feel like one surface changing what it
    holds, not like a page being torn out and another pushed in.
    """
    if duration is None:
        duration = t.DURATION_FAST

    if not _ENABLED:
        swap()
        return None

    effect = _opacity_effect(widget)
    out = QPropertyAnimation(effect, b"opacity", widget)
    out.setDuration(duration)
    out.setEasingCurve(curve())
    out.setStartValue(effect.opacity() or 1.0)
    out.setEndValue(0.0)

    def on_dark() -> None:
        swap()
        back = QPropertyAnimation(effect, b"opacity", widget)
        back.setDuration(t.DURATION_BASE)
        back.setEasingCurve(curve())
        back.setStartValue(0.0)
        back.setEndValue(1.0)
        back.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    out.finished.connect(on_dark)
    out.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return out


def flash(widget: QWidget, *, duration: int | None = None) -> None:
    """A single dip and recover.

    For an action whose only result is otherwise invisible: "marked unread"
    on a row that has already scrolled away, a setting that saved with no
    other change on screen. One dip, never a pulse - a repeating
    attention-getter in a mail client is something to be endured rather
    than read.
    """
    if not _ENABLED:
        return
    if duration is None:
        duration = t.DURATION_FAST

    effect = _opacity_effect(widget)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration * 2)
    anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.InOutQuad))
    anim.setKeyValueAt(0.0, 1.0)
    anim.setKeyValueAt(0.5, 0.35)
    anim.setKeyValueAt(1.0, 1.0)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def after(msec: int, fn, parent=None) -> QTimer:
    """A one-shot timer parented to something, so it cannot outlive it.

    QTimer.singleShot bound to a method on a widget that gets destroyed
    first is a crash; this dies with its parent instead.
    """
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.timeout.connect(fn)
    timer.start(msec)
    return timer


def reveal(widget: QWidget, *, offset: int = 6, duration: int | None = None):
    """Content arriving: a short rise into place, fading as it comes.

    ADAPTED FROM MAGIC UI'S BlurFade, minus the blur. That component
    animates `y: 6 -> 0`, `opacity: 0 -> 1` and `blur(6px) -> blur(0)`
    together, and the reason it reads as "materialising" rather than
    "appearing" is the combination: the offset gives the content
    somewhere to come FROM, and the fade stops the movement reading as a
    slide.

    THE BLUR IS DELIBERATELY DROPPED. In a browser it is one compositor
    property; in Qt it is a QGraphicsBlurEffect re-rasterising the whole
    widget every frame, which over a full message list is exactly the
    expense that buys an effect nobody asked for. The offset carries
    nearly all of the impression and costs nothing.

    THE RISE IS OPT-IN, because Qt has no general way to nudge a widget
    that a layout owns - moving it just fights the layout on the next
    resize. A widget that wants the offset declares a `revealOffset` Qt
    property and shifts its OWN painting by it (see
    EmailListView.revealOffset); everything else gets the fade alone,
    which is still correct, just quieter.

    Used where content changes CONTEXT - a different folder, a different
    message - and never for routine repaints. A list that re-revealed
    itself on every sync tick would be unreadable.
    """
    if duration is None:
        duration = t.DURATION_BASE

    widget.setVisible(True)
    has_offset = widget.metaObject().indexOfProperty("revealOffset") >= 0

    if not _ENABLED:
        _opacity_effect(widget).setOpacity(1.0)
        if has_offset:
            widget.setProperty("revealOffset", 0.0)
        return None

    effect = _opacity_effect(widget)
    fade = QPropertyAnimation(effect, b"opacity", widget)
    fade.setDuration(duration)
    fade.setEasingCurve(curve())
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    if has_offset:
        rise = QPropertyAnimation(widget, b"revealOffset", widget)
        rise.setDuration(duration)
        rise.setEasingCurve(curve())
        rise.setStartValue(float(offset))
        rise.setEndValue(0.0)
        rise.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return fade


# --------------------------------------------------------------- theme change

class _ThemeCurtain(QWidget):
    """The previous theme, held over one window while the new one opens
    beneath it.

    A texture brush over a path, not a clip: QPainter clips are aliased,
    and a hard-stepped circle edge travelling across a whole window for
    400ms is exactly the kind of cheapness the effect cannot afford.
    fillPath with the snapshot as the brush is antialiased and costs one
    fill per frame.
    """

    def __init__(self, window: QWidget, snapshot, centre, circle: bool):
        super().__init__(window)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setObjectName("themeCurtain")
        self._snapshot = snapshot
        self._centre = centre
        self._circle = circle
        self._radius = 0.0
        self._opacity = 1.0
        self.setGeometry(window.rect())
        self.show()
        self.raise_()

    def set_state(self, radius: float, opacity: float) -> None:
        self._radius = radius
        self._opacity = opacity
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        whole = QPainterPath()
        whole.addRect(QRectF(self.rect()))
        if self._circle:
            hole = QPainterPath()
            hole.addEllipse(self._centre, self._radius, self._radius)
            whole = whole.subtracted(hole)
        else:
            painter.setOpacity(self._opacity)
        painter.fillPath(whole, QBrush(self._snapshot))
        painter.end()


def _app_windows() -> list[QWidget]:
    from PySide6.QtWidgets import QApplication

    return [
        w for w in QApplication.topLevelWidgets()
        if w.isVisible()
        and w.windowType() in (Qt.WindowType.Window, Qt.WindowType.Dialog)
        and w.width() > 0 and w.height() > 0
    ]


def reveal_theme_change(apply, *, origin=None, windows=None):
    """Change the theme, and let the new one spread from where it was asked
    for.

    ADAPTED FROM MAGIC UI'S ANIMATED THEME TOGGLER, whose whole idea is a
    circle opening at the button and the page changing inside it: cause
    and effect in one place. The browser does it with the View
    Transitions API; natively it is a snapshot of each open window taken
    BEFORE the switch, laid over that window, with a growing hole cut in
    it. The expensive part - rebuilding the stylesheet - happens under the
    snapshot, so no half-switched frame is ever seen.

    `origin` is a GLOBAL point. The same circle is used for every window,
    so with Settings open over the main window the change runs out of the
    dialog and on across the window behind it as one continuous edge.
    With no origin (a keyboard shortcut has no place on screen) the old
    theme simply fades instead.

    Reduced motion: apply() and nothing else. Not a very fast reveal - no
    reveal.
    """
    if not _ENABLED:
        apply()
        return None

    from PySide6.QtCore import QPointF, QVariantAnimation

    targets = windows if windows is not None else _app_windows()
    curtains: list[_ThemeCurtain] = []
    reach = 0.0
    for window in targets:
        snapshot = window.grab()
        if origin is not None:
            local = window.mapFromGlobal(origin)
            centre = QPointF(local)
            w, h = window.width(), window.height()
            corners = ((0, 0), (w, 0), (0, h), (w, h))
            reach = max(reach, max(
                ((cx - centre.x()) ** 2 + (cy - centre.y()) ** 2) ** 0.5
                for cx, cy in corners
            ))
        else:
            centre = QPointF(0, 0)
        curtains.append(_ThemeCurtain(window, snapshot, centre, origin is not None))

    apply()

    if not curtains:
        return None

    anim = QVariantAnimation(curtains[0])
    anim.setDuration(t.DURATION_THEME)
    anim.setEasingCurve(curve())
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)

    def step(value) -> None:
        for curtain in list(curtains):
            try:
                curtain.set_state(float(value) * reach, 1.0 - float(value))
            except RuntimeError:        # its window closed mid-reveal
                curtains.remove(curtain)

    def done() -> None:
        for curtain in curtains:
            try:
                curtain.hide()
                curtain.deleteLater()
            except RuntimeError:
                pass

    anim.valueChanged.connect(step)
    anim.finished.connect(done)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim

"""The app's motion vocabulary.

WHY THIS FILE EXISTS. Animation was being written per widget: NavPill owns
a QPropertyAnimation on a float, AccentButton owns another, ToastHost owns
a third, and each one picked its own duration and curve at the call site.
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
    QTimer,
)
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

"""The opening bar: a hairline that fills as Unified actually starts.

WHY THIS IS NOT A QProgressBar. The startup indicator used to be a stock
Qt indeterminate QProgressBar - the sliding chip every Qt application on
earth shows, which says "something is happening" and nothing else, and
which reads as developer tooling rather than as this product. It is also
the one thing on screen during the only moment the user has nothing to
look at, so it is worth drawing properly.

WHAT MAKES IT UNIFIED'S RATHER THAN A BROWSER'S. It is a hairline the
exact width of the wordmark, sitting directly beneath it. A browser
progress bar spans the window and belongs to the chrome; this belongs to
the MARK. Nothing else on the screen moves, so a 2px line advancing under
"Unified" is both the only motion and unmistakably part of the identity.

=========================================================================
THE PROGRESS IS REAL, AND WHERE IT CANNOT BE, IT DOES NOT PRETEND

app/main.py runs four genuine initialization steps on a background
thread - legacy migration, mailbox decrypt, database open, main-window
construction - and each one reports as it begins. Those are the only
checkpoints this app actually has, so they are the only ones the bar
uses. There is no byte counter behind a database open and no percentage
worth inventing for it.

Two rules keep that honest:

  * MONOTONIC, AND NEVER COMPLETE UNTIL IT IS. Each stage animates the
    fill toward that stage's checkpoint and stops there. The bar reaches
    1.0 in exactly one place: finish(), called when initialization has
    really finished.
  * A LONG STAGE DOES NOT LOOK STALLED, WITHOUT LYING ABOUT IT. The
    travel to each checkpoint is deliberately slow (DURATION_REVEAL) and
    eased with the app's OutQuint, which decelerates hard and approaches
    its target asymptotically. A decrypt that takes four seconds shows a
    line still visibly creeping, and that line is still inside the
    segment the completed work has earned. It never creeps past a
    checkpoint it has not reached.

=========================================================================
FAST STARTUPS. On a small cache the whole sequence can be over in under
100ms, and a bar that appears and vanishes inside three frames is a
flash, not an animation. finish() therefore checks how long the bar has
actually been visible: if it is less than _MIN_VISIBLE_MS it completes
immediately and lets the window close without an outro, so a fast start
looks fast rather than looking broken. Nothing is ever delayed to make
room for the animation.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QElapsedTimer,
    QPropertyAnimation,
    QRectF,
    Qt,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from app.ui import motion, theme as t

# Thin enough to read as a rule rather than as a control. Two device-
# independent pixels, so it stays a deliberate hairline at 100% and a
# crisp one at 150% and 200% rather than disappearing.
BAR_HEIGHT = 2

# Slow on purpose - see the class docstring. This is the one duration in
# the app allowed to exceed DURATION_SLOW, because it is not a response
# to a user action: it is the shape of a wait.
DURATION_REVEAL = 900

# Below this, the bar never really played and should not pretend to.
_MIN_VISIBLE_MS = 260


class OpeningBar(QWidget):
    """A hairline that fills from left to right as real work completes."""

    def __init__(self, width: int, parent=None):
        super().__init__(parent)
        self.setFixedHeight(BAR_HEIGHT)
        self.setFixedWidth(width)
        self._progress = 0.0
        self._anim: QPropertyAnimation | None = None
        self._shown = QElapsedTimer()
        self._shown.start()

    # ------------------------------------------------------------ progress

    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, value: float) -> None:
        # Clamped and monotonic: a retarget can never walk the fill
        # backwards, which would read as work being undone.
        self._progress = max(self._progress, min(1.0, float(value)))
        self.update()

    progress = Property(float, _get_progress, _set_progress)

    def advance_to(self, fraction: float, *, duration: int = DURATION_REVEAL) -> None:
        """Ease toward a checkpoint this stage has genuinely earned."""
        fraction = max(0.0, min(1.0, float(fraction)))
        if fraction <= self._progress:
            return
        if self._anim is not None:
            self._anim.stop()
        if not motion.motion_enabled():
            self._set_progress(fraction)
            return
        anim = QPropertyAnimation(self, b"progress", self)
        anim.setDuration(duration)
        anim.setEasingCurve(motion.curve())
        anim.setStartValue(self._progress)
        anim.setEndValue(fraction)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim

    def finish(self, on_done) -> None:
        """Run the fill to 1.0, then hand back.

        The only place the bar is allowed to complete. `on_done` is always
        called exactly once, on every path through this method, including
        the fast-start and reduced-motion paths - a startup sequence whose
        completion callback can be skipped is a window that never opens.
        """
        too_fast = self._shown.elapsed() < _MIN_VISIBLE_MS
        if too_fast or not motion.motion_enabled():
            self._set_progress(1.0)
            on_done()
            return

        if self._anim is not None:
            self._anim.stop()
        anim = QPropertyAnimation(self, b"progress", self)
        # Faster than the stage travel: the work is done, and the only
        # thing left is to say so.
        anim.setDuration(t.DURATION_BASE)
        anim.setEasingCurve(motion.curve())
        anim.setStartValue(self._progress)
        anim.setEndValue(1.0)
        anim.finished.connect(on_done)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim

    def stop(self) -> None:
        """Halt wherever it is. For the failure path: a bar that keeps
        advancing while an error dialog explains that startup failed is
        the interface contradicting itself."""
        if self._anim is not None:
            self._anim.stop()
            self._anim = None

    # --------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        radius = BAR_HEIGHT / 2.0
        # The track is a hairline in its own right, so the mark keeps its
        # full width before anything has happened - the bar does not grow
        # out of nothing, it FILLS. Both tokens follow the theme, so this
        # reads correctly on the warm near-black and on parchment without
        # either being a special case.
        painter.setBrush(t.qcolor(t.BORDER))
        painter.drawRoundedRect(QRectF(self.rect()), radius, radius)

        if self._progress > 0.0:
            filled = QRectF(self.rect())
            filled.setWidth(filled.width() * self._progress)
            if filled.width() >= BAR_HEIGHT:
                painter.setBrush(QColor(t.ACCENT))
                painter.drawRoundedRect(filled, radius, radius)
        painter.end()

    def retheme(self) -> None:
        self.update()

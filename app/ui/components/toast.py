"""In-app toast notifications: a small stack of auto-dismissing cards
anchored to the window's top-right corner.

Translated from the visual reference's Notify() pattern - an accent-
striped card that slides in from the edge and carries a countdown bar
that shrinks over its lifetime - adapted to live *inside* the app window
as a child overlay rather than a separate top-level popup, so a toast
can never outlive the window, never gets its own taskbar entry, and needs
no OS-level notification permission. Desktop "new mail arrived" alerts
still go through Notifier (system tray); this is for things worth saying
while the window already has focus - sync errors, remove-account
confirmations, database-repair notices - that would otherwise be easy to
miss in the status bar.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Property,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui import theme as t


class _CountdownBar(QWidget):
    """A 2px bar that paints a filled fraction of its own width - animated
    via a plain float property (paint-only, no layout churn), the same
    technique components/toggle.py uses for its sliding knob."""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self._fraction = 1.0
        self.setFixedHeight(2)

    def _get_fraction(self) -> float:
        return self._fraction

    def _set_fraction(self, value: float) -> None:
        self._fraction = max(0.0, min(1.0, value))
        self.update()

    fraction = Property(float, _get_fraction, _set_fraction)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(t.qcolor(t.BORDER))
        painter.drawRoundedRect(self.rect(), 1, 1)
        painter.setBrush(self._color)
        width = round(self.width() * self._fraction)
        painter.drawRoundedRect(0, 0, width, self.height(), 1, 1)


class _ToastCard(QWidget):
    def __init__(self, title: str, message: str, kind: str,
                 duration_ms: int, on_dismiss, parent=None):
        super().__init__(parent)
        self.setObjectName("toastCard")
        self._on_dismiss = on_dismiss
        color = t.qcolor(t.TOAST_KIND_COLORS.get(kind, t.ACCENT))

        self._surface_color = t.qcolor(t.TOAST_BG)
        self._accent_color = color

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # The accent stripe is painted in paintEvent alongside the card
        # surface (clipped to the same rounded path) rather than being a
        # child widget - a child with its own border-radius can't follow
        # the parent's rounded corner cleanly, and it left a visible
        # square notch at the card's top-left and bottom-left.
        outer.addSpacing(t.TOAST_STRIPE_WIDTH)

        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(t.SPACE_MD, t.SPACE_SM + 1, t.SPACE_SM + 2, t.SPACE_SM)
        col.setSpacing(2)

        title_label = QLabel(title)
        title_label.setFont(t.make_font("status"))
        title_label.setStyleSheet(f"color: {color.name()};")
        title_label.setWordWrap(True)
        col.addWidget(title_label)

        if message:
            msg_label = QLabel(message)
            msg_label.setFont(t.make_font("caption"))
            msg_label.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
            msg_label.setWordWrap(True)
            col.addWidget(msg_label)

        col.addSpacing(4)
        self._bar = _CountdownBar(color)
        col.addWidget(self._bar)
        outer.addWidget(body, stretch=1)

        self.setFixedWidth(t.TOAST_WIDTH)
        # Child QLabels must not inherit a background - the card's own
        # paintEvent is the single thing that draws this surface.
        self.setStyleSheet("QWidget#toastCard QLabel { background: transparent; }")
        t.apply_elevation(self, "md")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to dismiss")

        self._countdown = QPropertyAnimation(self._bar, b"fraction", self)
        self._countdown.setDuration(duration_ms)
        self._countdown.setStartValue(1.0)
        self._countdown.setEndValue(0.0)
        self._countdown.setEasingCurve(QEasingCurve.Type.Linear)
        self._countdown.start()

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.dismiss)
        self._dismiss_timer.start(duration_ms)

        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._dismissed = False

    def slide_to(self, point: QPoint, *, animate: bool = True) -> None:
        if not animate:
            self.move(point)
            return
        self._slide.stop()
        self._slide.setDuration(t.TOAST_SLIDE_MS)
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(point)
        self._slide.start()

    def paintEvent(self, event) -> None:  # noqa: N802
        """Paint the card surface directly instead of relying on QSS.

        A QWidget *subclass* (which this is) does not paint a stylesheet
        `background` at all unless WA_StyledBackground is set - confirmed
        by rendering a toast over a magenta backdrop and finding the
        backdrop showing through the card body. Painting here is both the
        fix and the guarantee the surface is genuinely opaque and follows
        the rounded shape, including under the accent stripe.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        radius = t.RADIUS_MD
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # Opaque surface first - nothing behind the toast may show through.
        painter.fillPath(path, self._surface_color)

        # Accent stripe down the left edge, clipped to the same rounded
        # path so it curves with the corners instead of squaring them off.
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(
            QRectF(rect.left(), rect.top(),
                   float(t.TOAST_STRIPE_WIDTH), rect.height()),
            self._accent_color,
        )
        painter.restore()

        painter.setPen(QPen(t.qcolor(t.BORDER_LIGHT), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.dismiss()

    def dismiss(self) -> None:
        """Slide back out to the right while self-destructing once the
        animation ends. The host is told immediately (not after the slide
        finishes) so it can drop this card from the stack and reflow the
        others right away - otherwise a toast that arrives mid-exit would
        get its outbound animation redirected back into a stack slot."""
        if self._dismissed:
            return
        self._dismissed = True
        self._dismiss_timer.stop()
        self._countdown.stop()
        if self._on_dismiss:
            self._on_dismiss(self)
        exit_x = self.parent().width() if self.parent() else self.x() + self.width()
        self._slide.stop()
        self._slide.setDuration(t.TOAST_SLIDE_MS)
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(QPoint(exit_x, self.y()))
        self._slide.finished.connect(self.deleteLater)
        self._slide.start()


class ToastHost(QObject):
    """Owns the toast stack for one window. Install once with
    ToastHost(main_window) and call .show(...) from anywhere; toasts are
    parented to the window so they're clipped to it and destroyed with it.

    An event filter on the window keeps the stack pinned to the top-right
    corner across resizes/moves instead of a one-shot geometry calc.
    """

    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._toasts: list[_ToastCard] = []
        window.installEventFilter(self)

    def show(self, title: str, message: str = "", *, kind: str = "info",
              duration_ms: int | None = None) -> None:
        card = _ToastCard(
            title, message, kind,
            duration_ms or t.TOAST_DEFAULT_DURATION_MS,
            self._on_dismissed, parent=self._window,
        )
        # A fresh widget's sizeHint() isn't reliable until its layout has
        # actually run at least once - adjustSize() forces that
        # synchronously instead of waiting for the event loop to get
        # around to it, which otherwise raced two toasts arriving close
        # together into the same stack slot (both read the same stale,
        # pre-layout height and landed on top of each other).
        card.adjustSize()
        # Enter from just off the right edge of the window.
        start_x = self._window.width()
        card.move(start_x, self._next_y())
        card.show()
        card.raise_()
        self._toasts.append(card)
        self._relayout(animate=True)

    def _on_dismissed(self, card: _ToastCard) -> None:
        # The card animates its own exit and deletes itself; this only
        # needs to drop it from the stack so the others reflow to fill
        # the gap immediately.
        if card in self._toasts:
            self._toasts.remove(card)
        self._relayout(animate=True)

    def _stack_top(self) -> int:
        """Where the stack begins so that the newest card sits one margin
        above the bottom edge. Anchoring to the bottom keeps toasts clear
        of the command bar and the reading pane's action row, which live
        along the top edge - a top-right toast lands directly on top of
        Reply/Delete."""
        total = sum(card.height() for card in self._toasts)
        total += t.TOAST_SPACING * max(0, len(self._toasts) - 1)
        return max(t.TOAST_MARGIN, self._window.height() - t.TOAST_MARGIN - total)

    def _next_y(self) -> int:
        y = self._stack_top()
        for card in self._toasts:
            y += card.height() + t.TOAST_SPACING
        return y

    def _relayout(self, *, animate: bool) -> None:
        # Oldest at the top of the stack, newest along the bottom, so a
        # new toast never shoves the one being read out from under the
        # pointer.
        y = self._stack_top()
        x = self._window.width() - t.TOAST_WIDTH - t.TOAST_MARGIN
        for card in self._toasts:
            card.slide_to(QPoint(x, y), animate=animate)
            y += card.height() + t.TOAST_SPACING

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # Defensive: PySide6/shiboken can dispatch a queued event to this
        # filter in a narrow window around the owning widget's teardown
        # (observed when a process creates and discards more than one
        # window in the same run, e.g. tests) - a bare attribute-access
        # crash here must never propagate out of Qt's event dispatch.
        window = getattr(self, "_window", None)
        if window is None:
            return False
        if watched is window and event.type() in (
            QEvent.Type.Resize, QEvent.Type.Move,
        ):
            self._relayout(animate=False)
        return False

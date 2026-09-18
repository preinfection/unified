"""In-app toast notifications: a small stack of auto-dismissing cards
anchored to the window's top-right corner.

A card that slides in from the edge and carries a countdown bar that
shrinks over its lifetime, living *inside* the app window
as a child overlay rather than a separate top-level popup, so a toast
can never outlive the window, never gets its own taskbar entry, and needs
no OS-level notification permission.

NO ACCENT STRIPE. This card used to carry a 3px colored bar down its left
edge. A colored side-stripe is decoration standing in for meaning, and it
placed the only hue on the card in the spot least likely to be read. The
kind is carried by a leading dot in the semantic color instead: it sits
directly beside the title where the eye already is, and being a shape as
well as a hue it survives color blindness and a glance from the corner of
the eye. The countdown bar keeps the same color, so the card still reads
as one object. Desktop "new mail arrived" alerts
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

from app.ui import motion, theme as t


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


_DOT_SIZE = 8


class _KindDot(QWidget):
    """The toast's kind, as a shape in a semantic color.

    A painted circle rather than an SVG from assets/icons: there is no
    icon in the set that means "info" or "success" at 8px, and a glyph
    that small stops being a glyph anyway. What matters here is that the
    signal has an outline at all, so it is not carried by hue alone.
    """

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(_DOT_SIZE, _DOT_SIZE)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        painter.end()


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

        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(t.SPACE_MD + 2, t.SPACE_MD, t.SPACE_MD, t.SPACE_MD - 2)
        col.setSpacing(3)

        # Title row: the kind dot, then the title. The dot is the shape
        # half of the signal; the title stays in primary text so the
        # sentence is legible rather than tinted.
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(t.SPACE_SM)
        head.addWidget(_KindDot(color), 0, Qt.AlignmentFlag.AlignVCenter)

        title_label = QLabel(title)
        title_label.setFont(t.make_font("status"))
        t.role(title_label, "primary")
        title_label.setWordWrap(True)
        head.addWidget(title_label, 1)
        col.addLayout(head)

        if message:
            msg_label = QLabel(message)
            msg_label.setFont(t.make_font("caption"))
            t.role(msg_label, "secondary")
            msg_label.setWordWrap(True)
            # Indented to the title's left edge, past the dot column, so the
            # two lines read as one block instead of a hanging paragraph.
            msg_row = QHBoxLayout()
            msg_row.setContentsMargins(_DOT_SIZE + t.SPACE_SM, 0, 0, 0)
            msg_row.addWidget(msg_label)
            col.addLayout(msg_row)

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
        self._slide.setEasingCurve(motion.curve())

        self._dismissed = False

    def restart_timer(self, duration_ms: int) -> None:
        """Give this card its full life again.

        Used when the identical notice arrives a second time - see
        ToastHost.show. A fault that keeps recurring keeps its card on
        screen, which is what the repeat actually means, instead of
        stacking another copy of the same sentence beneath it.
        """
        if self._dismissed:
            return
        self._dismiss_timer.stop()
        self._dismiss_timer.start(duration_ms)
        self._countdown.stop()
        self._countdown.setDuration(duration_ms)
        self._countdown.setStartValue(1.0)
        self._countdown.setEndValue(0.0)
        self._countdown.start()

    def slide_to(self, point: QPoint, *, animate: bool = True) -> None:
        # The caller's `animate` AND the app-wide setting: a notice
        # that still slides in from the edge under reduced motion is
        # the largest movement left in the product.
        if not animate or not motion.motion_enabled():
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

        painter.setPen(QPen(t.qcolor(t.TOAST_BORDER), 1))
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

    An event filter on the window keeps the stack pinned to its corner
    across resizes/moves instead of a one-shot geometry calc.

    BOTTOM-RIGHT, NOT TOP-RIGHT, AND THIS IS A CORRECTNESS FIX RATHER THAN
    A PREFERENCE. The stack used to sit at y=TOAST_MARGIN, which is inside
    the toolbar: a sync-error toast covered the search field and the
    refresh and console buttons for four and a half seconds. Notifications
    do not get to sit on top of the controls, least of all the focused one
    - a toast over a focused text field is the "focus obscured" failure
    exactly. The bottom-right corner covers nothing, and is where desktop
    applications already put transient notices.

    Newest sits closest to the corner and older ones are pushed upward, so
    a placed toast only ever moves when one below it leaves.
    """

    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._toasts: list[_ToastCard] = []
        window.installEventFilter(self)

    #: Cards on screen whose title and body match exactly, keyed so a
    #: repeat can find and refresh one instead of stacking another.
    def _find_duplicate(self, title: str, message: str):
        for card in self._toasts:
            if card.property("toastKey") == (title, message):
                return card
        return None

    def show(self, title: str, message: str = "", *, kind: str = "info",
             duration_ms: int | None = None) -> None:
        """Raise a notice, or refresh the identical one already showing.

        REPEATS DO NOT STACK. Several of the events that reach here are
        per-account: three connected accounts whose stored sign-in has
        expired produce three RemoteActionWorker failures with the same
        title and the same body within a few hundred milliseconds, and the
        corner filled with three copies of one sentence. That is not more
        information, it is the same information three times, and it is the
        one case where a notification system most needs to be quiet.

        The existing card's dismiss timer restarts instead, so a fault
        that keeps recurring keeps its notice on screen - which is the
        behaviour that actually wanted, rather than a queue of identical
        cards the user has to sit through.
        """
        existing = self._find_duplicate(title, message)
        if existing is not None:
            existing.restart_timer(duration_ms or t.TOAST_DEFAULT_DURATION_MS)
            return

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
        card.setProperty("toastKey", (title, message))
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

    def _bottom_inset(self) -> int:
        """How much of the window's bottom edge is already spoken for.

        The status bar is a real widget with real text in it, so stacking
        over it would just trade one occlusion for another.
        """
        inset = t.TOAST_MARGIN
        status = getattr(self._window, "statusBar", None)
        if callable(status):
            try:
                bar = status()
                if bar is not None and bar.isVisible():
                    inset += bar.height()
            except RuntimeError:
                pass  # the window is being torn down under us
        return inset

    def _next_y(self) -> int:
        """Where a card about to be added will come to rest."""
        y = self._window.height() - self._bottom_inset()
        for card in self._toasts:
            y -= card.height() + t.TOAST_SPACING
        return y

    def _relayout(self, *, animate: bool) -> None:
        x = self._window.width() - t.TOAST_WIDTH - t.TOAST_MARGIN
        y = self._window.height() - self._bottom_inset()
        # Reversed: the newest card is last in the list and belongs
        # closest to the corner, with older ones stacking upward above it.
        for card in reversed(self._toasts):
            y -= card.height()
            card.slide_to(QPoint(x, y), animate=animate)
            y -= t.TOAST_SPACING

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

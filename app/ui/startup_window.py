"""The surface Unified opens on, and hands over to.

WHY THIS WINDOW EXISTS AT ALL. The real startup steps - legacy
migration, the AES-256-GCM decrypt of the local mailbox, opening the
database - take real time on a large cache and a slow disk, and they all
used to run before any window appeared. The app looked frozen for
however long that took. app/main.py runs them on a background thread and
reports each one here; nothing in this file is a timer pretending to be
progress.

=========================================================================
IT IS MAXIMIZED, AND THAT IS THE WHOLE TRANSITION

This was a 340x220 card in the middle of the screen, and the main window
was 1280x800. Startup therefore ended with a small box vanishing and a
differently shaped window appearing somewhere else - two unrelated
events, which is exactly the "a Qt window appeared and then suddenly
changed" feeling rather than "Unified is opening".

So this window opens maximized, on the app floor, with a normal frame -
the same geometry, the same background and the same title bar the shell
is about to occupy. The shell is then shown maximized BEHIND it and this
layer fades out. Nothing moves and nothing resizes: one surface resolves
into another. That fade IS the reveal, which is also why the shell
underneath does not run a second animation of its own - a tween playing
beneath a fading layer is invisible work that costs frames during the
one moment the app is trying to look immediate.

WHAT IS ON IT. The wordmark, the product's one standing claim
("Encrypted locally"), the opening bar, and a line naming the step that
is actually running. Centred, quiet, and no larger than it needs to be:
a maximized surface is a lot of room, and filling it would be the
opposite of the restraint the rest of the product is built on.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app import APP_NAME
from app.ui import motion, theme as t
from app.ui.components.opening_bar import OpeningBar
from app.ui.icons import make_app_icon
from app.ui.native_theme import apply_dark_titlebar
from app.ui.svg_icon import simple_icon

# A floor, for a font fallback narrow enough to make the block look like
# a fragment. The real width is measured from the content - see
# _mark_width - so the bar underlines the identity exactly rather than
# being set to a number somebody liked.
_MIN_MARK_WIDTH = 168

# The caption that sits under the bar, measured with it so the block has
# one right edge instead of a ragged one.
_CAPTION = "Encrypted locally"
_LOCK_SIZE = 12


def _mark_width() -> int:
    """How wide the identity block is, measured rather than chosen.

    The opening bar spans this, which makes it an underline for the whole
    mark - wordmark and claim together - instead of a bar that happens to
    sit near them. Measured at runtime because the resolved face depends
    on what Windows actually has (Segoe UI Variable, Segoe UI, Arial) and
    on the display scale, and a hard-coded width would be right on one
    machine and ragged on the next.
    """
    title = QFontMetrics(t.make_font("app_title")).horizontalAdvance(APP_NAME)
    caption = (
        _LOCK_SIZE + t.SPACE_XS + 2
        + QFontMetrics(t.make_font("caption")).horizontalAdvance(_CAPTION)
    )
    return max(_MIN_MARK_WIDTH, title, caption)


class StartupWindow(QWidget):
    #: Fractions the bar has genuinely earned by the time each stage
    #: BEGINS, keyed by the stage text app/main.py emits - so the two
    #: cannot drift apart silently. An unknown stage simply does not move
    #: the bar, rather than moving it somewhere invented.
    STAGE_PROGRESS = {
        "Checking install...": 0.12,
        "Unlocking encrypted mailbox...": 0.38,
        "Loading local cache...": 0.64,
        "Preparing mailbox...": 0.86,
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # THE USER CAN CLOSE THIS, AND IT BECAME MUCH EASIER TO. As a
        # 340x220 card almost nobody hit its X; as a maximized window with
        # a full title bar, closing it is an obvious thing to try while
        # waiting. Every public method below therefore checks this first,
        # because WA_DeleteOnClose destroys the C++ object and the
        # background init thread has no idea that happened - it calls
        # set_stage() a moment later and takes the whole process down with
        # "Internal C++ object already deleted".
        self._closed = False
        self._handing_over = False
        # A bare top-level QWidget is not covered by style.py's
        # QMainWindow/QDialog background rule, so it states its own or
        # risks painting as opaque black.
        self.setStyleSheet(f"background: {t.BG_APP};")
        apply_dark_titlebar(self, dark=t.is_dark())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_XXL, t.SPACE_XXL, t.SPACE_XXL, t.SPACE_XXL)
        root.setSpacing(0)
        # 5:6 rather than centred: the optical centre of a large empty
        # surface sits slightly above the true one, and EmptyState uses
        # the same ratio, so the two agree about where "middle" is.
        root.addStretch(5)

        mark = QVBoxLayout()
        mark.setSpacing(0)
        mark.setContentsMargins(0, 0, 0, 0)

        # THE SAME SIZE THE SIDEBAR SETS IT IN, deliberately. The wordmark
        # here is app_title, which is exactly what the sidebar masthead
        # uses, so the mark the user is looking at during startup is the
        # same weight as the one still sitting in the shell after the
        # reveal. Enlarging it for the splash would make the opening an
        # advertisement for a product whose own header is smaller.
        title = QLabel(APP_NAME)
        title.setFont(t.make_font("app_title"))
        t.role(title, "primary")
        mark.addWidget(title, 0, Qt.AlignmentFlag.AlignLeft)
        mark.addSpacing(t.SPACE_SM)

        width = _mark_width()
        self.bar = OpeningBar(width)
        mark.addWidget(self.bar, 0, Qt.AlignmentFlag.AlignLeft)
        mark.addSpacing(t.SPACE_MD)

        # The product's one standing claim, stated exactly as the sidebar
        # states it - the lock belongs to the sentence.
        secure = QHBoxLayout()
        secure.setContentsMargins(0, 0, 0, 0)
        secure.setSpacing(t.SPACE_XS + 2)
        self._lock = QLabel()
        self._lock.setPixmap(
            simple_icon("lock", _LOCK_SIZE, t.SECURE).pixmap(_LOCK_SIZE, _LOCK_SIZE)
        )
        secure.addWidget(self._lock, 0, Qt.AlignmentFlag.AlignVCenter)
        caption = QLabel(_CAPTION)
        caption.setFont(t.make_font("caption"))
        t.role(caption, "tertiary")
        secure.addWidget(caption, 0, Qt.AlignmentFlag.AlignVCenter)
        secure.addStretch(1)
        mark.addLayout(secure)
        mark.addSpacing(t.SPACE_XL)

        # What is actually running. Fixed height, so naming a longer step
        # cannot nudge the mark above it: the identity must not move while
        # the text under it changes.
        self._stage_label = QLabel("Starting")
        self._stage_label.setFont(t.make_font("caption"))
        t.role(self._stage_label, "tertiary")
        self._stage_label.setFixedHeight(
            QFontMetrics(t.make_font("caption")).height()
        )
        mark.addWidget(self._stage_label, 0, Qt.AlignmentFlag.AlignLeft)

        # The block is left-aligned within itself and centred as a unit. A
        # centred wordmark over a centred bar over centred prose is three
        # centre lines and no edge, which is what a splash screen looks
        # like; one shared left edge is what a page looks like.
        holder = QWidget()
        holder.setLayout(mark)
        holder.setFixedWidth(width)
        centred = QHBoxLayout()
        centred.setContentsMargins(0, 0, 0, 0)
        centred.addStretch(1)
        centred.addWidget(holder)
        centred.addStretch(1)
        root.addLayout(centred)
        root.addStretch(6)

        self._identity = holder

    def sizeHint(self) -> QSize:  # noqa: N802
        """The restore size, for the brief moment this window has one.

        Matches MainWindow's, so that if a window manager declines to
        maximize, what appears is still a sensibly proportioned window
        rather than whatever Qt would otherwise have guessed.
        """
        return QSize(1280, 800)

    def open_maximized(self) -> None:
        """Show filling the work area, then bring the identity up.

        showMaximized(), never a computed geometry: it is the only call
        that respects the taskbar, per-monitor DPI and whichever screen
        the window was placed on, and it leaves normal minimise / maximise
        / close behaviour intact. Nothing here hard-codes a resolution.
        """
        self.showMaximized()
        # Only the identity rises. Fading the whole window in would flash
        # the desktop through it, and the surface is already the right
        # colour from the first frame.
        motion.fade_in(self._identity, duration=t.DURATION_SLOW)

    # ------------------------------------------------------------- stages

    def bring_to_front(self) -> None:
        """Put the opening layer back above the shell, if it is still here.

        showMaximized() on the main window puts it in front on Windows, so
        the layer that is supposed to be covering it has to be raised
        again. Guarded because the user may have closed it in between, and
        raise_() on a destroyed widget is a hard crash.
        """
        if self._closed:
            return
        self.raise_()

    def was_cancelled(self) -> bool:
        """True when the user closed this window before startup finished.

        The caller has to ask, because "the opening surface is gone" and
        "the app should open anyway" are different situations and only
        main() can decide between them.
        """
        return self._closed and not self._handing_over

    def closeEvent(self, event) -> None:  # noqa: N802
        self._closed = True
        super().closeEvent(event)

    def set_stage(self, text: str) -> None:
        """Name the step that is starting, and advance the bar to what the
        steps before it have earned."""
        if self._closed:
            return  # the window is gone; the worker does not know yet
        self._stage_label.setText(text.rstrip(".").rstrip("…"))
        target = self.STAGE_PROGRESS.get(text)
        if target is not None:
            self.bar.advance_to(target)

    def finish(self, on_done) -> None:
        """Complete the bar, fade this layer away, and hand over.

        `on_done` runs once the window is gone, on every path - reduced
        motion and a startup too fast for the animation to have played
        included. A handover callback that can be skipped is an app that
        never finishes opening.
        """
        def fade_away() -> None:
            if not motion.motion_enabled():
                self.close()
                on_done()
                return
            # THE WHOLE WINDOW DISSOLVES, NOT ITS CONTENTS. Fading the
            # identity alone leaves the opening surface fully opaque over
            # the shell for the entire outro, so close() then snaps the
            # shell into existence - a cut dressed up as a fade, and the
            # exact transition this rewrite exists to remove. Window
            # opacity is composited by DWM, so the two maximized windows
            # cross-dissolve into each other for free.
            motion.animate_property(
                self, "windowOpacity", 0.0, duration=t.DURATION_BASE,
                on_done=lambda: (self.close(), on_done()),
            )

        self._handing_over = True
        if self._closed:
            # Already dismissed by the user. The handover still has to run
            # or nothing would ever show the shell - it just has no window
            # left to animate out.
            on_done()
            return
        self.bar.finish(fade_away)

    def fail(self) -> None:
        """Startup broke: stop the bar and get out of the way.

        A bar still advancing behind a dialog that says startup failed is
        the interface contradicting itself, and a splash left on screen
        with nothing behind it is an app that looks hung.
        """
        self._handing_over = True
        if self._closed:
            return
        self.bar.stop()
        self.close()

    def retheme(self) -> None:
        if self._closed:
            return
        self.setStyleSheet(f"background: {t.BG_APP};")
        self._lock.setPixmap(
            simple_icon("lock", _LOCK_SIZE, t.SECURE).pixmap(_LOCK_SIZE, _LOCK_SIZE)
        )
        self.bar.retheme()

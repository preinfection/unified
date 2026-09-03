"""The window shown while the app opens.

Opening Unified is not instant: it migrates a legacy install if there is
one, decrypts the local mailbox (AES-256-GCM, and a large cache on a slow
disk is real work), opens the database, and runs its integrity check. All
of that used to happen before any window appeared, so the app looked
frozen for however long it took. This appears the moment QApplication
exists and has no dependency on the database, the settings or any account
data.

What it is, and why:

* **A frameless card, not a small window.** A splash with an OS title bar,
  a caption and a close button reads as an application window that has
  not finished drawing. A rounded, shadowed card centred on screen reads
  as the product arriving. It paints itself, because Qt does not
  anti-alias a stylesheet's `border-radius` and a splash with stepped
  corners is worse than no splash.
* **Named steps, not a barber pole.** The startup sequence has four known
  stages, so the progress is a real fraction - four of four - rather than
  an indeterminate bar that says only "something is happening". The label
  says which stage in words.
* **The stage text swaps rather than blinks.** Same 150ms in-place swap
  the rest of the app uses when a line of text changes, so four stages in
  quick succession read as one line updating instead of as flicker.
* **Nothing is faked.** The fraction advances when `app/main.py` reports a
  step that has actually completed. There is no timer pretending to make
  progress.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from app import APP_NAME, __version__
from app.ui import theme as t
from app.ui.design import motion
from app.ui.design.motion import ValueAnimator, blend
from app.ui.icons import make_app_icon, make_mark

# The startup sequence, in order. `app/main.py` reports each one as it
# completes; the labels live here so the window owns its own copy.
STAGES = (
    "Checking your install",
    "Unlocking your mailbox",
    "Opening the local cache",
    "Preparing your mailbox",
)

_CARD_WIDTH = 380
_CARD_HEIGHT = 250
_SHADOW = 28          # room around the card for its drop shadow
_MARK = 44
_TRACK_WIDTH = 220
_TRACK_HEIGHT = 3


class StartupWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon())
        # Frameless and translucent so the card can have real rounded
        # corners and a shadow instead of sitting inside a square window.
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(_CARD_WIDTH + _SHADOW * 2, _CARD_HEIGHT + _SHADOW * 2)

        self._stage = 0
        self._label = "Starting Unified"
        self._previous_label = ""

        # The progress fill, and the in-place swap of the stage text.
        self._progress = ValueAnimator(self, 0.0, motion.DURATION_SLOW,
                                       motion.EASE_SMOOTH_OUT)
        self._swap = ValueAnimator(self, 0.0, motion.TEXT_SWAP,
                                   motion.EASE_IN_OUT, spatial=False)
        # The card settles in rather than appearing. Pure opacity, so it
        # survives reduced motion in shortened form.
        self._entrance = ValueAnimator(self, 1.0, motion.DURATION_MEDIUM,
                                       motion.EASE_SMOOTH_OUT, spatial=False)
        self._entrance.to(0.0)

        self._centre_on_screen()

    def _centre_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.move(available.center() - self.rect().center())

    # ----------------------------------------------------------------- api

    def set_stage(self, index: int, text: str = "") -> None:
        """Report a completed step. `index` is 1-based; the fraction and
        the label move together."""
        label = text or (STAGES[index - 1] if 0 < index <= len(STAGES) else "")
        if label and label != self._label:
            self._previous_label = self._label
            self._label = label
            self._swap.set_now(1.0)
            self._swap.to(0.0)
        self._stage = max(self._stage, index)
        self._progress.to(min(1.0, self._stage / len(STAGES)))

    def apply_theme(self) -> None:
        self.update()

    # --------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        palette = t.theme_manager.palette
        entrance = self._entrance.value
        painter.setOpacity(1.0 - entrance)

        card = QRectF(_SHADOW, _SHADOW, _CARD_WIDTH, _CARD_HEIGHT)
        radius = t.RADIUS_XL
        path = QPainterPath()
        path.addRoundedRect(card, radius, radius)

        # A soft, tinted shadow painted as concentric strokes: this window
        # is translucent, so a QGraphicsDropShadowEffect has nothing opaque
        # to cast from.
        shadow = QColor(palette.shadow)
        for step in range(10, 0, -1):
            ring = QColor(shadow)
            ring.setAlpha(max(2, int(shadow.alpha() / (step * 3.2))))
            painter.setPen(QPen(ring, step * 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                card.adjusted(-step, -step + 2, step, step + 2),
                radius + step, radius + step,
            )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.surface))
        painter.drawPath(path)

        painter.setPen(QPen(QColor(palette.border), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # The lit top edge every raised surface in the app carries.
        painter.save()
        painter.setClipPath(path)
        painter.setPen(QPen(QColor(palette.highlight), 1))
        painter.drawLine(
            card.left() + radius, card.top() + 0.75,
            card.right() - radius, card.top() + 0.75,
        )
        painter.restore()

        self._paint_content(painter, card, palette)
        painter.end()

    def _paint_content(self, painter: QPainter, card: QRectF, palette) -> None:
        centre_x = card.center().x()
        y = card.top() + 40

        painter.drawPixmap(
            int(centre_x - _MARK / 2), int(y), make_mark(_MARK, palette.accent)
        )
        y += _MARK + t.SPACE_XL

        title_font = t.make_font("title")
        painter.setFont(title_font)
        painter.setPen(QColor(palette.text_primary))
        title_height = QFontMetrics(title_font).height()
        painter.drawText(
            QRectF(card.left(), y, card.width(), title_height),
            Qt.AlignmentFlag.AlignHCenter, APP_NAME,
        )
        y += title_height + t.SPACE_2XS

        caption_font = t.make_font("caption")
        painter.setFont(caption_font)
        painter.setPen(QColor(palette.text_tertiary))
        caption_height = QFontMetrics(caption_font).height()
        painter.drawText(
            QRectF(card.left(), y, card.width(), caption_height),
            Qt.AlignmentFlag.AlignHCenter, "Your accounts, one mailbox",
        )

        # -- progress track, sitting above the stage line
        track_y = card.bottom() - 64
        track = QRectF(centre_x - _TRACK_WIDTH / 2, track_y,
                       _TRACK_WIDTH, _TRACK_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.surface_active))
        painter.drawRoundedRect(track, _TRACK_HEIGHT / 2, _TRACK_HEIGHT / 2)

        filled = max(_TRACK_HEIGHT, track.width() * self._progress.value)
        painter.setBrush(QColor(palette.accent))
        painter.drawRoundedRect(
            QRectF(track.left(), track.top(), filled, track.height()),
            _TRACK_HEIGHT / 2, _TRACK_HEIGHT / 2,
        )

        # -- the stage line, swapping in place
        stage_font = t.make_font("body_sm")
        painter.setFont(stage_font)
        stage_height = QFontMetrics(stage_font).height()
        stage_rect = QRectF(card.left(), track.bottom() + t.SPACE_XL,
                            card.width(), stage_height)
        swap = self._swap.value
        base = QColor(palette.text_secondary)

        if swap > 0.02 and self._previous_label:
            leaving = QColor(base)
            leaving.setAlphaF(max(0.0, 1.0 - swap * 1.8))
            painter.setPen(leaving)
            painter.drawText(
                stage_rect.translated(0, -motion.DISTANCE_MICRO * swap),
                Qt.AlignmentFlag.AlignHCenter, self._previous_label,
            )

        arriving = QColor(base)
        arriving.setAlphaF(max(0.0, 1.0 - swap))
        painter.setPen(arriving)
        painter.drawText(
            stage_rect.translated(0, motion.DISTANCE_MICRO * swap),
            Qt.AlignmentFlag.AlignHCenter, self._label,
        )

        # -- version, quiet, bottom right
        version_font = t.make_font("caption")
        painter.setFont(version_font)
        painter.setPen(blend(palette.text_tertiary, palette.surface, 0.35))
        painter.drawText(
            QRectF(card.left(), card.bottom() - 26, card.width() - t.SPACE_XL,
                   QFontMetrics(version_font).height()),
            Qt.AlignmentFlag.AlignRight, f"v{__version__}",
        )

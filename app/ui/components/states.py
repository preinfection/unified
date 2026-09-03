"""Empty, loading and error states.

These three are the surfaces most often left as an afterthought and most
often the first thing a new user sees, so they are built as first-class
components with the same rules:

* Say what happened, in a sentence a person would say out loud.
* Offer the next action when there is one, as a real button.
* Never show a spinner where the real progress is knowable, and never
  show a progress bar where it isn't - a fake percentage is worse than
  an honest indeterminate bar.
* Keep the illustration small. A 200px graphic above "Inbox is empty"
  fills the screen with an apology.

`SkeletonList` is the loading state for the message list specifically: it
paints the *shape* of rows that are about to arrive, which keeps the
layout from jumping when they do and reads as "loading" without a word.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme as t
from app.ui.components.buttons import Button, PrimaryButton
from app.ui.design import motion
from app.ui.svg_icon import themed_pixmap

_ICON_SIZE = 28


def _wrapping(label: QLabel, width: int) -> QLabel:
    """A word-wrapped QLabel pinned to a fixed measure."""
    label.setWordWrap(True)
    label.setFixedWidth(width)
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
    return label


def _set_wrapped(label: QLabel, text: str) -> None:
    """Set text on a `_wrapping` label and give it the height it needs.

    A word-wrapped QLabel reports a single line as its size hint, and a
    nested layout does not consult heightForWidth on its behalf - so
    without this the second line of every empty/error message is painted
    over whatever sits underneath it. Measuring against the label's own
    fixed width is deterministic, unlike hoping a size policy propagates
    through two layouts.
    """
    label.setText(text)
    label.setMinimumHeight(
        label.heightForWidth(label.width() or label.maximumWidth())
    )


class _CenteredPanel(QWidget):
    """Shared scaffolding: a vertically centered, width-capped column."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(t.SPACE_4XL, t.SPACE_4XL, t.SPACE_4XL, t.SPACE_4XL)
        outer.addStretch(2)
        self.column = QVBoxLayout()
        self.column.setSpacing(t.SPACE_MD)
        self.column.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(self.column)
        outer.addStretch(3)


class EmptyState(_CenteredPanel):
    """"Nothing here" as a designed moment rather than a blank pane."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column.addWidget(self._icon, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._title = QLabel("")
        self._title.setFont(t.make_font("subheading"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column.addWidget(self._title)

        self._detail = _wrapping(QLabel(""), 340)
        self._detail.setProperty("tone", "secondary")
        self._detail.setFont(t.make_font("body"))
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column.addWidget(self._detail, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._action = PrimaryButton("")
        self._action.setVisible(False)
        self._action_connected = False
        self.column.addSpacing(t.SPACE_XS)
        self.column.addWidget(self._action, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._icon_name = "inbox"

    def set_state(
        self, *, icon: str, title: str, detail: str = "",
        action_text: str = "", on_action=None,
    ) -> None:
        self._icon_name = icon
        self.refresh_icon()
        self._title.setText(title)
        _set_wrapped(self._detail, detail)
        self._detail.setVisible(bool(detail))
        self.setAccessibleName(f"{title}. {detail}" if detail else title)
        if action_text and on_action is not None:
            self._action.setText(action_text)
            if self._action_connected:
                self._action.clicked.disconnect()
            self._action.clicked.connect(on_action)
            self._action_connected = True
            self._action.setVisible(True)
        else:
            self._action.setVisible(False)

    def refresh_icon(self) -> None:
        self._icon.setPixmap(themed_pixmap(self._icon_name, _ICON_SIZE, "quiet"))


class ErrorState(_CenteredPanel):
    """Something failed. Says what, what it means, and how to retry -
    and keeps the technical detail available without leading with it."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column.addWidget(self._icon, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._title = QLabel("")
        self._title.setFont(t.make_font("subheading"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column.addWidget(self._title)

        self._detail = _wrapping(QLabel(""), 380)
        self._detail.setProperty("tone", "secondary")
        self._detail.setFont(t.make_font("body"))
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column.addWidget(self._detail, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._technical = QLabel("")
        self._technical.setProperty("tone", "tertiary")
        self._technical.setFont(t.make_font("caption", mono=True))
        self._technical.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _wrapping(self._technical, 380)
        self._technical.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._technical.setVisible(False)
        self.column.addWidget(self._technical, alignment=Qt.AlignmentFlag.AlignHCenter)

        row = QHBoxLayout()
        row.setSpacing(t.SPACE_MD)
        row.addStretch(1)
        self._retry = PrimaryButton("Try again", icon="refresh")
        self._retry.setVisible(False)
        self._details_btn = Button("Show details", variant="subtle", size="sm")
        self._details_btn.setVisible(False)
        self._details_btn.clicked.connect(self._toggle_details)
        row.addWidget(self._retry)
        row.addWidget(self._details_btn)
        row.addStretch(1)
        self.column.addSpacing(t.SPACE_XS)
        self.column.addLayout(row)

        self._retry_connected = False

    def set_state(
        self, *, title: str, detail: str = "", technical: str = "", on_retry=None,
    ) -> None:
        self.refresh_icon()
        self._title.setText(title)
        _set_wrapped(self._detail, detail)
        self._detail.setVisible(bool(detail))
        _set_wrapped(self._technical, technical)
        self._technical.setVisible(False)
        self._details_btn.setVisible(bool(technical))
        self._details_btn.setText("Show details")
        self.setAccessibleName(f"{title}. {detail}" if detail else title)
        if on_retry is not None:
            if self._retry_connected:
                self._retry.clicked.disconnect()
            self._retry.clicked.connect(on_retry)
            self._retry_connected = True
            self._retry.setVisible(True)
        else:
            self._retry.setVisible(False)

    def _toggle_details(self) -> None:
        showing = not self._technical.isVisible()
        self._technical.setVisible(showing)
        self._details_btn.setText("Hide details" if showing else "Show details")

    def refresh_icon(self) -> None:
        self._icon.setPixmap(themed_pixmap("warning", _ICON_SIZE, "danger"))


class LoadingState(_CenteredPanel):
    """First-sync progress. Real numbers when the sync knows them, an
    honest indeterminate bar when it doesn't - never a fake countdown."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._account = QLabel("")
        self._account.setFont(t.make_font("subheading"))
        self._account.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column.addWidget(self._account)

        self._status = QLabel("")
        self._status.setProperty("tone", "secondary")
        self._status.setFont(t.make_font("body"))
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setFixedWidth(320)
        self._bar.setTextVisible(False)
        self.column.addWidget(self._bar, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._detail = QLabel("")
        self._detail.setProperty("tone", "tertiary")
        self._detail.setFont(t.make_font("caption"))
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column.addWidget(self._detail)

    def set_state(
        self, account_email: str, status_text: str, detail_text: str,
        done: int = 0, total: int = 0,
    ) -> None:
        self._account.setText(account_email)
        self._status.setText(status_text)
        self._detail.setText(detail_text)
        self.setAccessibleName(f"{status_text} for {account_email}")
        if total:
            self._bar.setRange(0, total)
            self._bar.setValue(done)
        else:
            self._bar.setRange(0, 0)  # honest indeterminate


class SkeletonList(QWidget):
    """Placeholder message rows, painted at the real row geometry.

    Two jobs: tell the user the list is coming rather than empty, and
    reserve the exact space the real rows will take so nothing jumps when
    they land. A soft pulse carries the "still working" signal; it stops
    entirely under reduced motion, where the static shapes say the same
    thing without moving.
    """

    def __init__(self, rows: int = 8, parent=None):
        super().__init__(parent)
        self._rows = rows
        self._phase = 0.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not t.theme_manager.reduced_motion and not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        self.start()
        super().showEvent(event)

    def _tick(self) -> None:
        # One sweep per shimmer cycle, linear - a highlight travelling
        # across the placeholders, not the whole block throbbing.
        self._phase = (self._phase + 33 / motion.SHIMMER_CYCLE) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        base = QColor(t.BORDER)
        base.setAlpha(150)
        row_height = t.row_height()
        avatar = t.AVATAR_MD
        y = t.SPACE_XS
        width = self.width()
        while y + row_height < self.height() and (y // max(row_height, 1)) < self._rows:
            cy = y + (row_height - avatar) / 2
            painter.setBrush(base)
            painter.drawEllipse(QRectF(t.SPACE_LG, cy, avatar, avatar))
            left = t.SPACE_LG + avatar + t.SPACE_LG
            painter.drawRoundedRect(
                QRectF(left, y + row_height * 0.24, (width - left) * 0.42, 9),
                t.RADIUS_XS, t.RADIUS_XS,
            )
            painter.drawRoundedRect(
                QRectF(left, y + row_height * 0.52, (width - left) * 0.72, 8),
                t.RADIUS_XS, t.RADIUS_XS,
            )
            y += row_height

        # The travelling highlight band. Drawn over the placeholders and
        # clipped to them, so it reads as light moving across the shapes
        # rather than as a stripe across the pane.
        if self._timer.isActive():
            sweep = QLinearGradient()
            width = self.width()
            centre = (self._phase * 1.6 - 0.3) * width
            sweep.setStart(centre - width * 0.22, 0)
            sweep.setFinalStop(centre + width * 0.22, 0)
            highlight = QColor(t.BORDER_STRONG)
            highlight.setAlpha(0)
            sweep.setColorAt(0.0, highlight)
            mid = QColor(t.BORDER_STRONG)
            mid.setAlpha(90)
            sweep.setColorAt(0.5, mid)
            sweep.setColorAt(1.0, highlight)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceAtop
            )
            painter.fillRect(self.rect(), sweep)
        painter.end()

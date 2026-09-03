"""A small window shown the instant the app launches, before the
(potentially real work: decrypting the local cache, opening the
database) startup steps that used to run before any window appeared at
all - the app looked frozen for however long those took, especially the
AES-256-GCM decrypt of a large encrypted mailbox on a slow disk.

This window has no dependency on the database, settings, or account
data - it can be constructed and shown immediately after QApplication
exists. app/main.py runs the real init sequence on a background
_InitWorker thread and calls set_stage() as each real step completes;
nothing here is a fake timer-driven progress bar.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from app import APP_NAME
from app.ui import theme as t
from app.ui.icons import make_app_icon, make_mark
from app.ui.native_theme import apply_dark_titlebar


class StartupWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon())
        self.setFixedSize(380, 260)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # A bare top-level QWidget is not covered by the stylesheet's
        # QMainWindow/QDialog background rule, so it names its surface
        # explicitly rather than risk painting as opaque black.
        self.setObjectName("appRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#appRoot {{ background: {t.BG_CANVAS}; }}")
        apply_dark_titlebar(self)

        col = QVBoxLayout(self)
        col.setContentsMargins(t.SPACE_4XL, t.SPACE_4XL, t.SPACE_4XL, t.SPACE_4XL)
        col.setSpacing(0)
        col.addStretch(1)

        icon_label = QLabel()
        icon_label.setPixmap(make_mark(40, t.ACCENT))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(icon_label)
        col.addSpacing(t.SPACE_XL)

        title = QLabel(APP_NAME)
        title.setFont(t.make_font("title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(title)

        subtitle = QLabel("Your accounts, one mailbox")
        subtitle.setFont(t.make_font("body_sm"))
        subtitle.setProperty("tone", "tertiary")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(subtitle)
        col.addSpacing(t.SPACE_4XL)

        self._stage_label = QLabel("Starting Unified...")
        self._stage_label.setFont(t.make_font("body_sm"))
        self._stage_label.setProperty("tone", "secondary")
        self._stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._stage_label)
        col.addSpacing(t.SPACE_LG)

        self._bar = QProgressBar()
        # Indeterminate, not a fake countdown: these startup steps (file
        # decrypt, database open) don't have a byte-level progress figure
        # worth showing, but real background work genuinely is happening -
        # this is the same honest "still working" pattern LoadingState
        # already uses when a sync phase has no total yet.
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setFixedWidth(200)
        col.addWidget(self._bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        col.addStretch(1)

    def apply_theme(self) -> None:
        self.setStyleSheet(f"QWidget#appRoot {{ background: {t.BG_CANVAS}; }}")

    def set_stage(self, text: str) -> None:
        self._stage_label.setText(text)

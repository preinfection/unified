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
        self.setFixedSize(340, 220)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # A bare top-level QWidget isn't covered by style.py's QMainWindow/
        # QDialog background rule, so it gets its own explicit background
        # rather than risk showing through as opaque black.
        self.setStyleSheet(f"background: {t.BG_APP};")
        apply_dark_titlebar(self)

        col = QVBoxLayout(self)
        col.setContentsMargins(t.SPACE_XL, t.SPACE_XL, t.SPACE_XL, t.SPACE_XL)
        col.addStretch(1)

        icon_label = QLabel()
        icon_label.setPixmap(make_mark(44, t.TEXT_PRIMARY))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(icon_label)
        col.addSpacing(t.SPACE_MD)

        title = QLabel(APP_NAME)
        title.setFont(t.make_font("app_title"))
        title.setStyleSheet(f"color: {t.TEXT_PRIMARY};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(title)
        col.addSpacing(t.SPACE_LG)

        self._stage_label = QLabel("Starting Unified...")
        self._stage_label.setFont(t.make_font("body"))
        self._stage_label.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
        self._stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._stage_label)
        col.addSpacing(t.SPACE_SM)

        self._bar = QProgressBar()
        # Indeterminate, not a fake countdown: these startup steps (file
        # decrypt, database open) don't have a byte-level progress figure
        # worth showing, but real background work genuinely is happening -
        # this is the same honest "still working" pattern LoadingState
        # already uses when a sync phase has no total yet.
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setFixedWidth(240)
        col.addWidget(self._bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        col.addStretch(1)

    def set_stage(self, text: str) -> None:
        self._stage_label.setText(text)

"""A small accent tick + uppercase label, used to introduce a grouped
section within a dialog or panel (Settings' "General" / "Google account" /
"Connected accounts", the sidebar's "ACCOUNTS" list).

Translated from the visual reference's default section-header treatment -
a short accent-colored bar beside an uppercase, accent-tinted title -
which reads as a stronger section break than a plain gray caption label
without adding a full divider line. One widget so every section break in
the app uses the same tick weight/spacing/color instead of each screen
reinventing it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.ui import theme as t


class SectionHeader(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(t.SPACE_XS + 2)

        tick = QWidget()
        tick.setFixedSize(3, 11)
        tick.setStyleSheet(f"background: {t.ACCENT}; border-radius: 1px;")
        row.addWidget(tick, alignment=Qt.AlignmentFlag.AlignVCenter)

        label = QLabel(text.upper())
        label.setFont(t.make_font("section_label"))
        label.setStyleSheet(f"color: {t.ACCENT};")
        row.addWidget(label, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming convention)
        label = self.findChild(QLabel)
        if label is not None:
            label.setText(text.upper())


class DialogHeading(QWidget):
    """A dialog's in-body title: a taller accent stripe beside the heading
    text, standing in for the reference's title-bar accent stripe now that
    every dialog draws its own heading inside the body rather than relying
    on the OS title bar. Used by Settings/Compose/Add Account so a dialog's
    identity reads the same way the sidebar masthead and email rows do.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(t.SPACE_SM)

        stripe = QWidget()
        stripe.setFixedSize(4, 20)
        stripe.setStyleSheet(f"background: {t.ACCENT}; border-radius: 2px;")
        row.addWidget(stripe, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._label = QLabel(text)
        self._label.setFont(t.make_font("dialog_heading"))
        row.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming convention)
        self._label.setText(text)

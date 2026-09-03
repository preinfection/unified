"""Section headings.

Two of them, doing genuinely different jobs:

* `SectionHeader` introduces a group *inside* a surface - the sidebar's
  ACCOUNTS list, a settings group. It is a quiet uppercase overline with
  an optional trailing action, not a colored bar with an accent tick. A
  section break should be the least interesting thing on the screen; the
  moment every group announces itself in accent color, the one thing
  that genuinely needs the accent (the active row) has to compete.
* `DialogHeading` names a whole surface. It is a real heading in the type
  ramp with an optional one-line subtitle underneath, so a dialog opens
  with a sentence explaining itself rather than a bare noun.

Both expose `setText` in Qt's spelling because they stand in for QLabel
at their call sites.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui import theme as t


class SectionHeader(QWidget):
    def __init__(self, text: str, action: QWidget | None = None, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(t.SPACE_MD, 0, t.SPACE_XS, 0)
        row.setSpacing(t.SPACE_SM)

        self._label = QLabel(text.upper())
        self._label.setProperty("role", "overline")
        self._label.setFont(t.make_font("overline"))
        row.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        if action is not None:
            row.addWidget(action, alignment=Qt.AlignmentFlag.AlignVCenter)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming convention)
        self._label.setText(text.upper())


class DialogHeading(QWidget):
    def __init__(self, text: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(t.SPACE_2XS)

        self._label = QLabel(text)
        self._label.setFont(t.make_font("heading"))
        col.addWidget(self._label)

        self._subtitle = QLabel(subtitle)
        self._subtitle.setProperty("tone", "secondary")
        self._subtitle.setFont(t.make_font("body_sm"))
        self._subtitle.setWordWrap(True)
        self._subtitle.setVisible(bool(subtitle))
        col.addWidget(self._subtitle)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming convention)
        self._label.setText(text)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

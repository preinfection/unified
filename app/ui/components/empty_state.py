"""A centered icon + title + detail placeholder, reused everywhere the
message list has nothing to show: no accounts yet, an empty folder, or a
search with no matches. One component so every "nothing here" moment in
the app looks intentional instead of just... blank.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui import theme as t
from app.ui.svg_icon import simple_icon


class EmptyState(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.addStretch(2)

        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._icon)
        col.addSpacing(t.SPACE_MD)

        self._title = QLabel("")
        self._title.setFont(t.make_font("dialog_heading"))
        self._title.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._title)

        self._detail = QLabel("")
        self._detail.setFont(t.make_font("body"))
        self._detail.setStyleSheet(f"color: {t.TEXT_TERTIARY};")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        self._detail.setFixedWidth(320)
        col.addWidget(self._detail, alignment=Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(t.SPACE_LG)

        self._action = QPushButton("")
        self._action.setObjectName("composeButton")
        self._action.setFont(t.make_font("button"))
        self._action.setVisible(False)
        self._action_connected = False
        col.addWidget(self._action, alignment=Qt.AlignmentFlag.AlignHCenter)
        col.addStretch(3)

    def set_state(
        self, *, icon: str, title: str, detail: str = "",
        action_text: str = "", on_action=None,
    ) -> None:
        self._icon.setPixmap(simple_icon(icon, 40, t.BORDER_LIGHT).pixmap(40, 40))
        self._title.setText(title)
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        if action_text and on_action is not None:
            self._action.setText(f"  {action_text}")
            if self._action_connected:
                self._action.clicked.disconnect()
            self._action.clicked.connect(on_action)
            self._action_connected = True
            self._action.setVisible(True)
        else:
            self._action.setVisible(False)

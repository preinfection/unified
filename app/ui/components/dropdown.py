"""A custom-painted dropdown: a styled button that opens a floating,
animated options popup - replacing the platform-default look of a plain
QComboBox anywhere the choice is prominent enough to be worth it (the
compose "From" account picker, the Add Account type picker).

Translated from the reference's dropdown pattern: a popup parented above
the rest of the window, a checkmark on the selected row instead of a
highlighted-row-only cue, and a fade + settle-into-place entrance instead
of an instant appear/disappear. Built on Qt.WindowType.Popup so outside-
click-to-close and focus-loss-to-close come for free from Qt itself,
rather than a hand-rolled full-screen backdrop widget.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui import theme as t
from app.ui.svg_icon import simple_icon

_POPUP_MAX_VISIBLE = 8


class _DropdownPopup(QWidget):
    picked = Signal(object)

    def __init__(self, items: list[tuple[str, object]], current: object, anchor: QWidget):
        super().__init__(anchor.window(), Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("dropdownPopup")
        outer.addWidget(card)
        t.apply_elevation(card, "md")

        col = QVBoxLayout(card)
        col.setContentsMargins(5, 5, 5, 5)
        col.setSpacing(1)

        width = max(anchor.width(), 160)
        for label, value in items:
            row = QPushButton(label)
            row.setObjectName("dropdownOption")
            row.setFlat(True)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setMinimumWidth(width - 10)
            row.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            if value == current:
                row.setIcon(simple_icon("check", 12, t.ACCENT))
                row.setProperty("selected", True)
            row.clicked.connect(lambda _=False, v=value: self._pick(v))
            col.addWidget(row)

        self.setFixedWidth(width)

    def _pick(self, value: object) -> None:
        self.picked.emit(value)
        self.close()

    def show_animated(self, target: QPoint) -> None:
        start = QPoint(target.x(), target.y() - 8)
        self.move(start)
        self.setWindowOpacity(0.0)
        self.show()
        self._pos_anim = QPropertyAnimation(self, b"pos", self)
        self._pos_anim.setDuration(t.DURATION_BASE)
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pos_anim.setStartValue(start)
        self._pos_anim.setEndValue(target)
        self._pos_anim.start()
        self._op_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._op_anim.setDuration(t.DURATION_BASE)
        self._op_anim.setStartValue(0.0)
        self._op_anim.setEndValue(1.0)
        self._op_anim.start()


class Dropdown(QWidget):
    """items: a list of (label, value) pairs. value can be anything
    equality-comparable (a dict, an id, a plain string)."""

    changed = Signal(object)

    def __init__(self, items: list[tuple[str, object]] | None = None,
                 current: object = None, parent=None):
        super().__init__(parent)
        self._items: list[tuple[str, object]] = items or []
        self._current = current
        self._popup: _DropdownPopup | None = None

        self.setObjectName("dropdownButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(t.HEIGHT_MD)

        row = QHBoxLayout(self)
        row.setContentsMargins(t.SPACE_MD, 0, t.SPACE_SM + 2, 0)
        row.setSpacing(t.SPACE_XS)
        self._label = QLabel()
        self._label.setFont(t.make_font("field_value"))
        row.addWidget(self._label, stretch=1)
        chevron = QLabel()
        chevron.setPixmap(simple_icon("chevron_down", 11, t.TEXT_SECONDARY).pixmap(11, 11))
        row.addWidget(chevron)

        if self._items and self._current is None:
            self._current = self._items[0][1]
        self._refresh_label()

    # ------------------------------------------------------------------ api

    def set_items(self, items: list[tuple[str, object]], current: object = None) -> None:
        self._items = items
        self._current = current if current is not None else (items[0][1] if items else None)
        self._refresh_label()

    def value(self) -> object:
        return self._current

    def set_value(self, value: object, *, emit: bool = True) -> None:
        self._current = value
        self._refresh_label()
        if emit:
            self.changed.emit(value)

    def _refresh_label(self) -> None:
        text = ""
        for label, value in self._items:
            if value == self._current:
                text = label
                break
        self._label.setText(text)

    # -------------------------------------------------------------- events

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._items:
            self._open()
        super().mousePressEvent(event)

    def _open(self) -> None:
        popup = _DropdownPopup(self._items, self._current, self)
        popup.picked.connect(self._on_picked)
        self._popup = popup
        target = self.mapToGlobal(QPoint(0, self.height() + 4))
        popup.show_animated(target)

    def _on_picked(self, value: object) -> None:
        self.set_value(value)

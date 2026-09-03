"""A styled select control.

`QComboBox` is styleable up to a point and then fights back: its popup is
a native view whose item metrics, checkmark and hover behavior come from
the platform style, so a themed combo box in a dark app still opens a
light-gray list on Windows. Where the choice is prominent - the compose
"From" account, the account-type picker - this replaces it with a styled
button plus a real `Qt.WindowType.Popup`.

Building on `Popup` rather than a hand-rolled overlay is deliberate:
click-outside-to-close, focus-loss-to-close and correct stacking come
from Qt itself. What is added on top is the part Qt does not give for
free - full keyboard operation (Up/Down/Home/End/Enter/Esc), a checkmark
on the current value rather than relying on highlight alone, and an
entrance that settles into place instead of appearing.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme as t
from app.ui.svg_icon import themed, themed_pixmap

_POPUP_MAX_VISIBLE = 10


class _DropdownPopup(QWidget):
    picked = Signal(object)

    def __init__(self, items: list[tuple[str, object]], current: object, anchor: QWidget):
        super().__init__(anchor.window(), Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._buttons: list[QPushButton] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("dropdownPopup")
        outer.addWidget(card)
        t.apply_elevation(card, "md")

        column = QVBoxLayout(card)
        column.setContentsMargins(t.SPACE_XS, t.SPACE_XS, t.SPACE_XS, t.SPACE_XS)
        column.setSpacing(1)

        width = max(anchor.width(), 200)
        for label, value in items[:_POPUP_MAX_VISIBLE * 4]:
            row = QPushButton(label)
            row.setObjectName("dropdownOption")
            row.setFlat(True)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setMinimumWidth(width - 2 * t.SPACE_XS)
            row.setFont(t.make_font("menu_item"))
            if value == current:
                row.setIcon(themed("check", t.ICON_XS, "accent"))
                row.setProperty("selected", True)
            row.clicked.connect(lambda _=False, v=value: self._pick(v))
            column.addWidget(row)
            self._buttons.append(row)

        self.setFixedWidth(width)
        self._focus_index = next(
            (i for i, (_l, v) in enumerate(items) if v == current), 0
        )

    def _pick(self, value: object) -> None:
        self.picked.emit(value)
        self.close()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._buttons:
            self._buttons[min(self._focus_index, len(self._buttons) - 1)].setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        if not self._buttons:
            return super().keyPressEvent(event)
        try:
            index = self._buttons.index(self.focusWidget())
        except ValueError:
            index = 0
        if key == Qt.Key.Key_Down:
            index = (index + 1) % len(self._buttons)
        elif key == Qt.Key.Key_Up:
            index = (index - 1) % len(self._buttons)
        elif key == Qt.Key.Key_Home:
            index = 0
        elif key == Qt.Key.Key_End:
            index = len(self._buttons) - 1
        else:
            return super().keyPressEvent(event)
        self._buttons[index].setFocus()
        event.accept()

    def show_animated(self, target: QPoint) -> None:
        duration = t.duration(t.DURATION_BASE)
        if not duration:
            self.move(target)
            self.show()
            return
        start = QPoint(target.x(), target.y() - 6)
        self.move(start)
        self.setWindowOpacity(0.0)
        self.show()
        self._pos_anim = QPropertyAnimation(self, b"pos", self)
        self._pos_anim.setDuration(duration)
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pos_anim.setStartValue(start)
        self._pos_anim.setEndValue(target)
        self._pos_anim.start()
        self._op_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._op_anim.setDuration(duration)
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
        # A *custom* QWidget subclass does not paint its stylesheet
        # background at all unless this is set - Qt's own widget classes
        # do, which is why the omission is so easy to miss.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(t.CONTROL_MD)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Selection")

        row = QHBoxLayout(self)
        row.setContentsMargins(t.SPACE_LG, 0, t.SPACE_MD, 0)
        row.setSpacing(t.SPACE_SM)
        self._label = QLabel()
        self._label.setFont(t.make_font("field_value"))
        row.addWidget(self._label, stretch=1)
        self._chevron = QLabel()
        self._chevron.setPixmap(themed_pixmap("chevron_down", t.ICON_XS, "quiet"))
        row.addWidget(self._chevron)

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
        self.setAccessibleDescription(text)

    def refresh_icon(self) -> None:
        self._chevron.setPixmap(themed_pixmap("chevron_down", t.ICON_XS, "quiet"))

    # -------------------------------------------------------------- events

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._items:
            self._open()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Down,
        ):
            self._open()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        t.set_variant(self, "focused", "true")
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        t.set_variant(self, "focused", None)
        super().focusOutEvent(event)

    def _open(self) -> None:
        if not self._items:
            return
        popup = _DropdownPopup(self._items, self._current, self)
        popup.picked.connect(self._on_picked)
        self._popup = popup
        popup.show_animated(self.mapToGlobal(QPoint(0, self.height() + 4)))

    def _on_picked(self, value: object) -> None:
        self.set_value(value)
        self.setFocus()

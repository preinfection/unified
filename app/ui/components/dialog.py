"""One dialog anatomy, used by every dialog in the app.

Before this, each dialog laid itself out from scratch: different margins,
different heading treatment, buttons in whatever order they were written,
and `QMessageBox` for confirmations - which on Windows draws in the OS
style and lands in the middle of a dark application looking like it came
from a different decade.

`AppDialog` fixes the anatomy:

    ┌───────────────────────────────┐
    │ Heading                       │  title + optional one-line subtitle
    │ ───────────────────────────── │
    │ body (whatever the caller adds)│
    │ ───────────────────────────── │
    │ [status]        Cancel  Primary│  destructive actions sit far left
    └───────────────────────────────┘

and the behavior:

* Enter activates the primary action, Esc cancels - and Esc is refused
  while a dialog is busy, so a half-finished sign-in cannot be abandoned
  by a stray keypress.
* Focus starts on the first real input, not on the Cancel button.
* Button order is fixed: secondary actions left, the confirming action
  last, destructive actions separated from both.

`confirm`, `warn` and `report_error` are the QMessageBox replacements,
so a confirmation looks like the rest of the product.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme as t
from app.ui.components.buttons import Button, DangerButton, PrimaryButton
from app.ui.components.section_header import DialogHeading
from app.ui.native_theme import apply_dark_titlebar


def divider(orientation: str = "horizontal") -> QFrame:
    line = QFrame()
    line.setProperty("role", "divider")
    if orientation == "vertical":
        line.setProperty("orientation", "vertical")
        line.setFixedWidth(1)
    else:
        line.setFixedHeight(1)
    return line


class AppDialog(QDialog):
    """Base class for every dialog in Unified."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        parent=None,
        width: int = 480,
        show_dividers: bool = True,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.setModal(True)
        apply_dark_titlebar(self)

        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_3XL, t.SPACE_2XL, t.SPACE_3XL, t.SPACE_2XL)
        root.setSpacing(t.SPACE_XL)

        self.heading = DialogHeading(title, subtitle)
        root.addWidget(self.heading)
        if show_dividers:
            root.addWidget(divider())

        self.body = QVBoxLayout()
        self.body.setSpacing(t.SPACE_LG)
        root.addLayout(self.body, stretch=1)

        if show_dividers:
            root.addWidget(divider())

        footer = QHBoxLayout()
        footer.setSpacing(t.SPACE_MD)
        self._destructive_slot = QHBoxLayout()
        self._destructive_slot.setSpacing(t.SPACE_MD)
        footer.addLayout(self._destructive_slot)

        self.status = QLabel("")
        self.status.setProperty("tone", "secondary")
        self.status.setFont(t.make_font("status"))
        self.status.setWordWrap(True)
        footer.addWidget(self.status, stretch=1)

        self._action_slot = QHBoxLayout()
        self._action_slot.setSpacing(t.SPACE_MD)
        footer.addLayout(self._action_slot)
        root.addLayout(footer)

    # ------------------------------------------------------------- body

    def add_body(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    # ---------------------------------------------------------- buttons

    def add_action(self, button: Button, *, primary: bool = False) -> Button:
        """Add a footer action. The confirming action goes last, which is
        the Windows convention this app follows everywhere."""
        self._action_slot.addWidget(button)
        if primary:
            button.setDefault(True)
            button.setAutoDefault(True)
        return button

    def add_destructive(self, button: Button) -> Button:
        """A destructive action is separated from the confirm/cancel pair
        so it can never be hit by muscle memory aiming at 'OK'."""
        self._destructive_slot.addWidget(button)
        return button

    def set_status(self, text: str, *, tone: str = "secondary") -> None:
        t.set_variant(self.status, "tone", tone)
        self.status.setText(text)

    # -------------------------------------------------------------- busy

    def set_busy(self, busy: bool, message: str = "") -> None:
        """Busy means: in-flight work the user should not double-start,
        and must not lose by pressing Esc."""
        self._busy = busy
        if message or not busy:
            self.set_status(message)

    @property
    def is_busy(self) -> bool:
        return self._busy

    def reject(self) -> None:
        if self._busy:
            return
        super().reject()


class MessageDialog(AppDialog):
    """A confirmation/notice styled like the rest of the product."""

    def __init__(
        self,
        title: str,
        message: str,
        *,
        confirm_text: str = "OK",
        cancel_text: str | None = None,
        destructive: bool = False,
        detail: str = "",
        parent=None,
    ):
        super().__init__(title, parent=parent, width=420, show_dividers=False)
        text = QLabel(message)
        text.setWordWrap(True)
        text.setFont(t.make_font("body"))
        self.add_body(text)

        if detail:
            extra = QLabel(detail)
            extra.setWordWrap(True)
            extra.setProperty("tone", "tertiary")
            extra.setFont(t.make_font("body_sm"))
            extra.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.add_body(extra)

        if cancel_text:
            cancel = Button(cancel_text, variant="secondary")
            cancel.clicked.connect(self.reject)
            self.add_action(cancel)

        confirm_cls = DangerButton if destructive else PrimaryButton
        confirm = confirm_cls(confirm_text)
        confirm.clicked.connect(self.accept)
        self.add_action(confirm, primary=True)
        confirm.setFocus()


def confirm(
    parent,
    title: str,
    message: str,
    *,
    confirm_text: str = "Confirm",
    cancel_text: str = "Cancel",
    destructive: bool = False,
    detail: str = "",
) -> bool:
    dialog = MessageDialog(
        title, message, confirm_text=confirm_text, cancel_text=cancel_text,
        destructive=destructive, detail=detail, parent=parent,
    )
    return bool(dialog.exec())


def notify(parent, title: str, message: str, *, detail: str = "") -> None:
    MessageDialog(title, message, confirm_text="OK", detail=detail, parent=parent).exec()


def report_error(parent, title: str, message: str, *, detail: str = "") -> None:
    """An error the user must acknowledge. The plain-language sentence
    leads; the provider's own wording is kept underneath rather than
    thrown away or shown as the headline."""
    MessageDialog(
        title, message, confirm_text="Close", detail=detail, parent=parent
    ).exec()

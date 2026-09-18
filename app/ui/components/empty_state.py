"""A centered placeholder, reused everywhere the message list has nothing
to show: no accounts yet, an empty folder, or a search with no matches.
One component so every "nothing here" moment in the app looks intentional
instead of just blank.

TYPE LEADS, THE ICON FOLLOWS. This used to open with a 40px outlined glyph
in BORDER_LIGHT, which at that value is barely visible and reads as an
image that failed to load rather than as a mark. An empty state's job is to
say what is happening and what to do about it, and both of those are
sentences. The icon is smaller, dimmer and set beneath the type now: it
confirms the message rather than announcing it.

The title also moved from secondary to PRIMARY text. A heading that is the
only thing on the screen should not be the second-dimmest thing on it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui import theme as t
from app.ui.components.primitives import Button, Variant
from app.ui.svg_icon import simple_icon


class EmptyState(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setSpacing(0)
        # 5:6 rather than 2:3 - an optical centre sits a little above the
        # true one, and at 2:3 this block visibly floated high.
        col.addStretch(5)

        self._title = QLabel("")
        self._title.setFont(t.make_font("section_heading"))
        t.role(self._title, "primary")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._title)
        col.addSpacing(t.SPACE_SM)

        # A WRAPPED LABEL MUST NOT BE ADDED WITH AN ALIGNMENT FLAG, and
        # this cost the "No results" state its second line. QVBoxLayout
        # gives an aligned child its sizeHint rather than stretching it,
        # and a word-wrapped QLabel's sizeHint is its ONE-LINE height - so
        # a detail that wrapped to two lines was allocated the height of
        # one and rendered straight through the heading above it. Centring
        # is done by a row that carries the stretches instead, which leaves
        # the label a normal, height-for-width child of a column.
        self._detail = QLabel("")
        self._detail.setFont(t.make_font("body"))
        t.role(self._detail, "secondary")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        self._detail.setFixedWidth(330)
        detail_row = QWidget()
        dr = QHBoxLayout(detail_row)
        dr.setContentsMargins(0, 0, 0, 0)
        dr.addStretch(1)
        dr.addWidget(self._detail)
        dr.addStretch(1)
        self._detail_row = detail_row
        col.addWidget(detail_row)

        self._action_gap = QWidget()
        self._action_gap.setFixedHeight(t.SPACE_XL)
        col.addWidget(self._action_gap)

        # THE SHARED PRIMARY BUTTON, not the compose action's identity.
        # This carried objectName="composeButton" - at the time the only
        # filled button style with a name - so "Add account" was literally
        # wearing the toolbar's compose button, and restyling one silently
        # restyled the other. It is a Button(PRIMARY) now, like every other
        # primary action in the app.
        self._action = Button("", Variant.PRIMARY)
        self._action.setVisible(False)
        self._action_connected = False
        col.addWidget(self._action, alignment=Qt.AlignmentFlag.AlignHCenter)

        col.addSpacing(t.SPACE_XXL)
        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._icon)
        col.addStretch(6)

    def retheme(self) -> None:
        """Re-tint the glyph. Text follows the stylesheet; a pixmap cannot."""
        if getattr(self, "_icon_name", ""):
            self._icon.setPixmap(
                simple_icon(self._icon_name, 22, t.TEXT_TERTIARY).pixmap(22, 22)
            )

    def set_state(
        self, *, icon: str, title: str, detail: str = "",
        action_text: str = "", on_action=None,
    ) -> None:
        # THE ICON IS DROPPED WHEN THERE IS AN ACTION. "Add account" under a
        # plus-in-a-circle says the same thing twice, and the glyph ends up
        # below the button competing with it for the eye. The icon earns its
        # place only on the states that have no button - an empty Trash, a
        # search with no matches - where it is the one non-text cue.
        self._icon_name = icon
        self._icon.setPixmap(simple_icon(icon, 22, t.TEXT_TERTIARY).pixmap(22, 22))
        self._icon.setVisible(not action_text)
        self._title.setText(title)
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        self._detail_row.setVisible(bool(detail))
        if action_text and on_action is not None:
            self._action.setText(f"  {action_text}")
            if self._action_connected:
                self._action.clicked.disconnect()
            self._action.clicked.connect(on_action)
            self._action_connected = True
            self._action.setVisible(True)
            self._action_gap.setVisible(True)
        else:
            self._action.setVisible(False)
            # The gap goes with the button. Left in place it put 24px of
            # nothing between the detail line and the icon on every state
            # that has no action, which is most of them.
            self._action_gap.setVisible(False)

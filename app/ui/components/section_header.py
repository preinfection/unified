"""Section breaks: the small uppercase label that introduces a group
(Settings' "General" / "Connected accounts", the sidebar's "Accounts"), and
the larger heading a dialog opens with.

BOTH OF THESE USED TO CARRY A COLORED STRIPE. SectionHeader had a 3px
accent tick beside an accent-tinted title; DialogHeading had a 4px accent
stripe beside the heading text. Neither survives, for the same reason the
nav pill's left bar did not: a short colored bar next to a label is
ornament wearing the costume of a system, and putting the app's single
brightest value on a static label spends it on the least important thing
on the screen. A section label's job is to be found when looked for and
ignored otherwise, which is a job for size, weight, letter-spacing and
color VALUE, not for hue.

What replaces the tick is a rule that runs from the end of the label to the
edge of the container. That is a real typographic device, it says "this
group starts here and extends across this width", and unlike a stripe it
scales with the panel instead of sitting in the corner of it.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.ui import theme as t
# The hairline is the shared primitive, not a third implementation of it.
# There were three copies of "a 1px QFrame filled with t.BORDER" in this
# codebase - here, in settings_dialog._divider, and in primitives.Rule -
# and the two local ones baked the colour into an inline stylesheet, which
# made them precisely the two that stayed dark after a switch to the light
# palette. Rule carries objectName "rule" and is coloured by the app
# stylesheet, so it re-themes with everything else.
from app.ui.components.primitives import Rule as _Rule


class SectionHeader(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(t.SPACE_SM + 2)

        self._label = QLabel(text.upper())
        self._label.setFont(t.make_font("section_label"))
        t.role(self._label, "tertiary")
        row.addWidget(self._label, 0)
        row.addWidget(_Rule(), 1)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming convention)
        self._label.setText(text.upper())


class DialogHeading(QWidget):
    """A dialog's in-body title.

    Type alone now: 20px semibold with a hair of negative tracking, which
    at this size is what makes a heading look set rather than merely
    enlarged. It is the only thing on its line, so it needs no help being
    found.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self._label = QLabel(text)
        self._label.setFont(t.make_font("dialog_heading"))
        t.role(self._label, "primary")
        row.addWidget(self._label)
        row.addStretch(1)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming convention)
        self._label.setText(text)

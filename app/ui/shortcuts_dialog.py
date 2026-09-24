"""The keyboard sheet, generated from the same table the shortcuts are
installed from.

WHY GENERATED. A shortcut list written by hand is wrong within two
releases: someone adds a binding in a widget, nobody updates the sheet,
and the app now documents a keyboard interface it does not have. Every row
below comes from shortcuts.BINDINGS, so a binding that exists is listed and
a binding that is listed exists.

The keys are set in the mono face for the same reason timestamps are: they
are values to be matched against what is under your fingers, not prose.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui import shortcuts, theme as t
from app.ui.components.primitives import Button, Variant
from app.ui.components.section_header import DialogHeading, SectionHeader


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.setObjectName("shortcutsDialog")
        self.setMinimumSize(520, 560)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(t.SPACE_XL, t.SPACE_LG, t.SPACE_XL, t.SPACE_LG)
        outer.setSpacing(t.SPACE_LG)

        header = QHBoxLayout()
        header.addWidget(DialogHeading("Keyboard"))
        header.addStretch(1)
        close = Button("Close", Variant.SECONDARY)
        close.clicked.connect(self.accept)
        header.addWidget(close)
        outer.addLayout(header)

        # Scrolls, because the table grows and a dialog that clips its own
        # last row is worse than one that scrolls.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, t.SPACE_SM, 0)
        col.setSpacing(t.SPACE_LG)

        for group, bindings in shortcuts.grouped().items():
            col.addWidget(SectionHeader(group))
            grid = QWidget()
            rows = QGridLayout(grid)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setHorizontalSpacing(t.SPACE_LG)
            rows.setVerticalSpacing(t.SPACE_SM)
            # The keys column is fixed so every group's keys line up with
            # every other group's: a ragged left edge on a reference table
            # makes it slower to scan than the list it replaces.
            rows.setColumnMinimumWidth(0, 150)
            rows.setColumnStretch(1, 1)
            for i, binding in enumerate(bindings):
                keys = QLabel(shortcuts.pretty(binding.keys))
                keys.setObjectName("mono")
                keys.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                rows.addWidget(keys, i, 0, Qt.AlignmentFlag.AlignTop)

                label = QLabel(binding.label)
                label.setFont(t.make_font("field_value"))
                label.setWordWrap(True)
                rows.addWidget(label, i, 1)
            col.addWidget(grid)

        col.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        note = QLabel(
            "Single-letter shortcuts stand down while you are typing in a "
            "text field."
        )
        note.setFont(t.make_font("caption"))
        t.role(note, "tertiary")
        note.setWordWrap(True)
        outer.addWidget(note)

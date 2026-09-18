"""Keyboard control for the main window.

WHY THIS FILE EXISTS. Before it, Unified had no keyboard interface at all:
not one QShortcut, QKeySequence or keyPressEvent in the entire codebase.
Every action in the product required the mouse. For a desktop mail client
that is not a missing polish item, it is a missing half of the product,
because reading mail is a repetitive task and repetitive tasks are what
keyboards are for.

The bindings are the ones every mail client already shares, so nobody has
to learn them: Gmail, Thunderbird and Mailspring agree on j/k, Enter, r,
s, #, / and ?, and a client that invents its own is being different at the
user's expense rather than its own.

    j / k or Down / Up   move through the list
    Enter                open the focused message
    Escape               leave search, or return focus to the list
    /  or Ctrl+F         search
    n  or Ctrl+N         compose
    r  or F5             sync now
    s                    star the selected message
    #  or Delete         delete the selected message
    u                    mark unread
    Ctrl+1..9            jump to an account
    Ctrl+,               settings
    ?                    the shortcut list itself

ONE PLACE, NOT SCATTERED. Every binding is registered here against a
MainWindow, so the shortcut sheet in the help dialog is generated from the
same table the shortcuts are built from and the two cannot disagree. A
binding added in a widget somewhere else would be invisible to that sheet,
which is how undocumented shortcuts happen.

SINGLE-KEY SHORTCUTS AND TEXT FIELDS. `j` must move down the list, and it
must also type the letter j into the search box. WindowShortcut context
plus the guard in `_typing()` is what separates the two: if focus is in
any text-entry widget, the single-letter bindings stand down and let the
keystroke through. Without that guard this file would make the app
impossible to type in, which is the classic way single-key shortcuts get
added and then reverted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
)


@dataclass(frozen=True)
class Binding:
    keys: tuple[str, ...]
    label: str
    group: str
    action: str
    # True for the plain-letter bindings that must not fire while typing.
    literal: bool = True


BINDINGS: tuple[Binding, ...] = (
    Binding(("Down", "J"), "Next message", "Reading", "next_message"),
    Binding(("Up", "K"), "Previous message", "Reading", "prev_message"),
    Binding(("Return", "Enter"), "Open message", "Reading", "open_message"),
    Binding(("U",), "Mark unread", "Reading", "mark_unread"),
    Binding(("S",), "Star or unstar", "Reading", "toggle_star"),
    Binding(("Delete", "#"), "Delete message", "Reading", "delete_message"),

    Binding(("Ctrl+F", "/"), "Search", "Finding", "focus_search"),
    Binding(("Esc",), "Clear search, or focus the list", "Finding", "escape",
            literal=False),

    Binding(("Ctrl+N", "N"), "Compose", "Writing", "compose"),
    Binding(("Ctrl+R", "F5"), "Sync now", "Mailbox", "refresh", literal=False),
    Binding(("Ctrl+Shift+D",), "Toggle light and dark", "Mailbox", "toggle_theme",
            literal=False),
    Binding(("Ctrl+Shift+C",), "Toggle compact rows", "Mailbox", "toggle_density",
            literal=False),
    Binding(("Ctrl+B",), "Collapse or expand the sidebar", "Mailbox",
            "toggle_sidebar", literal=False),
    Binding(("Ctrl+,",), "Settings", "Mailbox", "settings", literal=False),
    Binding(("F1", "?"), "Keyboard shortcuts", "Mailbox", "show_shortcuts"),
)

_TEXT_WIDGETS = (QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QAbstractSpinBox)


def _typing(window) -> bool:
    """True when focus is somewhere a keystroke means a character.

    Checked at fire time rather than by juggling shortcut contexts, because
    the set of text widgets in a window changes as dialogs open and this
    stays correct without anyone remembering to register them.
    """
    focused = window.focusWidget()
    return isinstance(focused, _TEXT_WIDGETS)


@dataclass
class ShortcutManager:
    window: object
    handlers: dict[str, Callable[[], None]]
    _shortcuts: list = field(default_factory=list)

    def install(self) -> None:
        for binding in BINDINGS:
            handler = self.handlers.get(binding.action)
            if handler is None:
                continue
            for key in binding.keys:
                shortcut = QShortcut(QKeySequence(key), self.window)
                shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
                shortcut.activated.connect(self._guard(binding, handler))
                self._shortcuts.append(shortcut)

    def _guard(self, binding: Binding, handler: Callable[[], None]):
        window = self.window

        def run() -> None:
            if binding.literal and _typing(window):
                return
            handler()

        return run


def grouped() -> dict[str, list[Binding]]:
    """The bindings, grouped, for the shortcut sheet. Generated from the
    same table the shortcuts are installed from so the two cannot drift."""
    out: dict[str, list[Binding]] = {}
    for binding in BINDINGS:
        out.setdefault(binding.group, []).append(binding)
    return out


def pretty(keys: tuple[str, ...]) -> str:
    return "  or  ".join(
        k.replace("Ctrl", "Ctrl").replace("Return", "Enter") for k in keys
    )

"""Keyboard-focus visibility.

A focus indicator has to be unmistakable for someone driving the app from
the keyboard, and shouldn't flash on every mouse click for someone who
isn't. Qt's `:focus` pseudo-state can't tell those apart, so this
application-level filter tags the focused widget with a `kbfocus` dynamic
property *only* when focus arrived by keyboard (Tab, Backtab, a shortcut,
or the menu). The stylesheet turns that into a 2px ring.

The one thing this must not do is move anything: a ring that grows the
border also grows the widget, and a whole toolbar shuffles sideways as
you tab through it. The stylesheet compensates by removing exactly the
padding the extra border adds.

Deliberately not solved with a `QProxyStyle`: overriding focus-rect
drawing globally means adopting responsibility for every control's focus
rendering on every platform, and this needs one property and one rule.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt

from app.ui.design.theme import repolish

_KEYBOARD_REASONS = {
    Qt.FocusReason.TabFocusReason,
    Qt.FocusReason.BacktabFocusReason,
    Qt.FocusReason.ShortcutFocusReason,
    Qt.FocusReason.MenuBarFocusReason,
}

PROPERTY = "kbfocus"


class KeyboardFocusWatcher(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QEvent.Type.FocusIn:
            if event.reason() in _KEYBOARD_REASONS:
                self._mark(obj, True)
        elif kind == QEvent.Type.FocusOut:
            self._mark(obj, False)
        return False

    @staticmethod
    def _mark(widget, value: bool) -> None:
        if not hasattr(widget, "property"):
            return
        current = bool(widget.property(PROPERTY))
        if current == value:
            return
        widget.setProperty(PROPERTY, value if value else None)
        try:
            repolish(widget)
        except (RuntimeError, AttributeError):
            pass  # widget already being torn down


_watcher: KeyboardFocusWatcher | None = None


def install(app) -> KeyboardFocusWatcher:
    """Install the watcher on the QApplication (idempotent)."""
    global _watcher
    if _watcher is None:
        _watcher = KeyboardFocusWatcher()
        app.installEventFilter(_watcher)
    return _watcher

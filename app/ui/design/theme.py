"""The one thing that knows what the app currently looks like.

`ThemeManager` owns the active palette, the list density, and whether
motion is allowed, and it is the only object permitted to answer those
questions. Widgets ask it (via `app.ui.theme`, the thin facade the rest
of the codebase imports) instead of each deciding for itself - which is
what makes a live light/dark switch a signal connection rather than an
application restart.

Three things happen on every theme change, in this order:

1. the active `Palette` swaps, so anything that reads a token *at paint
   time* (delegates, painted indicators) is correct on its next repaint;
2. `QApplication.palette()` is rebuilt, so unstyled and native-drawn
   pieces (text cursors, selection in editors, tooltips, disabled text)
   follow along instead of staying dark on a light window;
3. the application stylesheet is re-rendered and re-applied, which Qt
   turns into a repolish of every widget.

Reduced motion is read from the OS rather than exposed as one more
setting: Windows' "Show animations" accessibility toggle is the answer
the user already gave.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette

from app.ui.design import tokens
from app.ui.design.palette import DARK, LIGHT, PALETTES, Palette

log = logging.getLogger(__name__)

MODE_SYSTEM = "system"
MODE_DARK = "dark"
MODE_LIGHT = "light"
MODES = (MODE_SYSTEM, MODE_LIGHT, MODE_DARK)


def _windows_prefers_light() -> bool | None:
    """Windows' per-app light/dark preference, or None if unknowable."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return bool(value)
    except OSError:
        return None


def _system_reduced_motion() -> bool:
    """True when the OS asks applications not to animate.

    Windows exposes this as SPI_GETCLIENTAREAANIMATION (the "Show
    animations in Windows" switch under Settings > Accessibility > Visual
    effects). Best effort: any failure means "animation is fine", which
    is the same answer as a machine that has never been configured.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        SPI_GETCLIENTAREAANIMATION = 0x1042
        enabled = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
        )
        return bool(ok) and not enabled.value
    except Exception:  # pragma: no cover - platform quirk, never fatal
        return False


class ThemeManager(QObject):
    """Singleton-ish: use the module-level `theme_manager` instance."""

    changed = Signal()          # palette and/or stylesheet changed
    density_changed = Signal()  # message-list density changed

    def __init__(self) -> None:
        super().__init__()
        self._mode = MODE_SYSTEM
        self._palette = self._resolve(MODE_SYSTEM)
        self._density = tokens.DENSITY_DEFAULT
        self._reduced_motion = _system_reduced_motion()

    # ------------------------------------------------------------ palette

    @staticmethod
    def _resolve(mode: str) -> Palette:
        if mode == MODE_LIGHT:
            return LIGHT
        if mode == MODE_DARK:
            return DARK
        prefers_light = _windows_prefers_light()
        # Dark is the product's default character; "system" only overrides
        # it when the OS says something definite.
        return LIGHT if prefers_light else DARK

    @property
    def palette(self) -> Palette:
        return self._palette

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_dark(self) -> bool:
        return self._palette.is_dark

    def color(self, role: str) -> str:
        return self._palette.color(role)

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown theme mode: {mode!r}")
        resolved = self._resolve(mode)
        unchanged = mode == self._mode and resolved is self._palette
        self._mode = mode
        self._palette = resolved
        if not unchanged:
            self.apply()
            self.changed.emit()

    # ------------------------------------------------------------ density

    @property
    def density(self) -> str:
        return self._density

    @property
    def row_height(self) -> int:
        return tokens.DENSITY_METRICS[self._density][0]

    @property
    def row_lines(self) -> int:
        return tokens.DENSITY_METRICS[self._density][1]

    def set_density(self, density: str) -> None:
        if density not in tokens.DENSITY_METRICS:
            raise ValueError(f"unknown density: {density!r}")
        if density == self._density:
            return
        self._density = density
        self.density_changed.emit()

    # ------------------------------------------------------------- motion

    @property
    def reduced_motion(self) -> bool:
        return self._reduced_motion

    def duration(self, base_ms: int) -> int:
        """The duration an animation should actually run for. Returns 0
        when the OS asks for reduced motion, so every animated component
        can call this instead of each one re-checking the setting (and
        one of them forgetting)."""
        return 0 if self._reduced_motion else base_ms

    # -------------------------------------------------------------- apply

    def build_qpalette(self) -> QPalette:
        """A QPalette so unstyled/native-drawn parts of Qt agree with the
        stylesheet. QSS cannot reach text cursors, editor selection
        colors, or the disabled color group - QPalette can."""
        p = self._palette
        qp = QPalette()
        c = QColor

        qp.setColor(QPalette.ColorRole.Window, c(p.canvas))
        qp.setColor(QPalette.ColorRole.WindowText, c(p.text_primary))
        qp.setColor(QPalette.ColorRole.Base, c(p.surface))
        qp.setColor(QPalette.ColorRole.AlternateBase, c(p.canvas))
        qp.setColor(QPalette.ColorRole.Text, c(p.text_primary))
        qp.setColor(QPalette.ColorRole.PlaceholderText, c(p.text_tertiary))
        qp.setColor(QPalette.ColorRole.Button, c(p.surface))
        qp.setColor(QPalette.ColorRole.ButtonText, c(p.text_primary))
        qp.setColor(QPalette.ColorRole.BrightText, c(p.danger_fg))
        qp.setColor(QPalette.ColorRole.Highlight, c(p.accent_solid))
        qp.setColor(QPalette.ColorRole.HighlightedText, c(p.text_on_accent))
        qp.setColor(QPalette.ColorRole.Link, c(p.text_link))
        qp.setColor(QPalette.ColorRole.LinkVisited, c(p.accent_fg))
        qp.setColor(QPalette.ColorRole.ToolTipBase, c(p.overlay))
        qp.setColor(QPalette.ColorRole.ToolTipText, c(p.text_primary))

        disabled = QPalette.ColorGroup.Disabled
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.ButtonText):
            qp.setColor(disabled, role, c(p.text_disabled))
        qp.setColor(disabled, QPalette.ColorRole.Highlight, c(p.surface_active))
        qp.setColor(disabled, QPalette.ColorRole.HighlightedText, c(p.text_disabled))

        inactive = QPalette.ColorGroup.Inactive
        qp.setColor(inactive, QPalette.ColorRole.Highlight, c(p.selected_inactive))
        qp.setColor(inactive, QPalette.ColorRole.HighlightedText, c(p.text_primary))
        return qp

    def apply(self, app=None) -> None:
        """Push the active theme onto the QApplication."""
        from PySide6.QtWidgets import QApplication

        app = app or QApplication.instance()
        if app is None:
            return
        from app.ui.design.stylesheet import render_stylesheet

        app.setPalette(self.build_qpalette())
        app.setStyleSheet(render_stylesheet(self._palette))


theme_manager = ThemeManager()


def repolish(widget) -> None:
    """Re-evaluate one widget's QSS after a dynamic property changed.

    Cheaper and far more targeted than re-applying the application
    stylesheet, which repolishes the entire widget tree.
    """
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_variant(widget, name: str, value) -> None:
    """Set a semantic dynamic property and repolish just that widget.

    Dynamic properties are how a plain QPushButton becomes a "primary"
    or "danger" button without a subclass per appearance - the stylesheet
    selects on `[variant="primary"]` and Qt keeps every native behavior
    (focus, keyboard activation, accessibility) that a hand-painted
    clickable QWidget would have thrown away.
    """
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    repolish(widget)

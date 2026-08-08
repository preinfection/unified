"""Forces the Windows title bar to match the app's dark theme instead of
whatever the system theme would otherwise apply.

Uses the DWM (Desktop Window Manager) API directly via ctypes - PySide6
has no cross-platform wrapper for this because it's a Windows-only
concept. Every call is best-effort: on Windows 10 builds that predate
these attributes, DwmSetWindowAttribute simply returns a failure HRESULT,
which is caught and ignored, falling back to the OS default title bar
rather than raising.
"""

from __future__ import annotations

import ctypes
import logging
import sys

from app.ui import theme as t

log = logging.getLogger(__name__)

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_CAPTION_COLOR = 35  # Windows 11 22000+
_DWMWA_TEXT_COLOR = 36     # Windows 11 22000+


def _colorref(hex_value: str) -> int:
    """Convert '#rrggbb' to a Win32 COLORREF (0x00BBGGRR)."""
    hex_value = hex_value.lstrip("#")
    r, g, b = (int(hex_value[i:i + 2], 16) for i in (0, 2, 4))
    return (b << 16) | (g << 8) | r


def apply_dark_titlebar(window) -> None:
    """Best-effort: dark caption background matching the app, light caption
    text/controls, and immersive dark mode enabled so a light system theme
    can't turn it white. No-ops silently if unsupported (older Windows 10)
    or non-Windows.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        dwmapi = ctypes.windll.dwmapi

        enable_dark = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(enable_dark), ctypes.sizeof(enable_dark),
        )

        caption = ctypes.c_int(_colorref(t.BG_APP))
        dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_CAPTION_COLOR,
            ctypes.byref(caption), ctypes.sizeof(caption),
        )

        text = ctypes.c_int(_colorref(t.TEXT_PRIMARY))
        dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text),
        )
    except Exception as e:
        log.debug("Could not set a custom title bar color: %s", e)

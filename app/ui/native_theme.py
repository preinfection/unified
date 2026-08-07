"""Forces a plain white Windows title bar, matching the app's
black-and-white design instead of whatever gray the system theme applies.

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

log = logging.getLogger(__name__)

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_CAPTION_COLOR = 35  # Windows 11 22000+
_DWMWA_TEXT_COLOR = 36     # Windows 11 22000+

_WHITE = 0x00FFFFFF        # COLORREF (0x00BBGGRR); all channels 255 either way
_DARK_TEXT = 0x00202020    # near-black, readable on white


def apply_white_titlebar(window) -> None:
    """Best-effort: white caption background, dark caption text/controls,
    and immersive dark mode disabled so a system dark theme can't turn it
    gray. No-ops silently if unsupported (older Windows 10) or non-Windows.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        dwmapi = ctypes.windll.dwmapi

        disable_dark = ctypes.c_int(0)
        dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(disable_dark), ctypes.sizeof(disable_dark),
        )

        caption = ctypes.c_int(_WHITE)
        dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_CAPTION_COLOR,
            ctypes.byref(caption), ctypes.sizeof(caption),
        )

        text = ctypes.c_int(_DARK_TEXT)
        dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text),
        )
    except Exception as e:
        log.debug("Could not set a custom title bar color: %s", e)

"""Launch the real application end to end, then close it.

Proves what no widget test can: that app/main.py's startup sequence -
legacy migration, cache decrypt, database open, MainWindow construction,
first paint - actually completes. Points APPDATA at a throwaway directory
first, so running this never touches the real encrypted mailbox.

    python tools/launch_check.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Before importing app.config, which reads APPDATA at import time.
SANDBOX = Path(tempfile.mkdtemp(prefix="unified-launch-"))
os.environ["APPDATA"] = str(SANDBOX)
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app.main as m  # noqa: E402

RESULT: dict = {}


def _inspect() -> None:
    """Look at what startup actually built, then close it."""
    from app.ui import theme
    from app.ui.main_window import MainWindow

    windows = QApplication.topLevelWidgets()
    main = next((w for w in windows if isinstance(w, MainWindow)), None)
    RESULT["main_window"] = main is not None
    if main is not None:
        screen = main.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry()   # the work area: taskbar excluded
        full = screen.geometry()                 # the whole physical screen

        RESULT["visible"] = main.isVisible()
        RESULT["size"] = (main.width(), main.height())
        RESULT["maximized"] = main.isMaximized()
        RESULT["fullscreen"] = main.isFullScreen()
        # A maximized window fills the WORK AREA, and the comparison has to
        # be against frameGeometry(): height() is the CLIENT area, which
        # excludes the title bar, so measuring that against the work area
        # is short by exactly one title bar and looks like a failure.
        # Filling the full screen geometry instead would mean covering the
        # taskbar - the one thing explicitly not wanted here.
        frame = main.frameGeometry()
        RESULT["fills_work_area"] = (
            abs(frame.height() - available.height()) <= 8
            and abs(frame.width() - available.width()) <= 8
        )
        RESULT["covers_taskbar"] = frame.height() > full.height() - 4
        RESULT["frameless"] = bool(
            main.windowFlags() & __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.WindowType.FramelessWindowHint
        )
        RESULT["rows"] = main.email_list.row_count()
        RESULT["shortcuts"] = len(main._shortcuts._shortcuts)
        RESULT["theme"] = theme.MODE
        RESULT["restore_size"] = (main.normalGeometry().width(),
                                  main.normalGeometry().height())
        main.close()
    app = QApplication.instance()
    if app is not None:
        app.quit()


# QApplication.exec cannot be monkeypatched (it takes no arguments as an
# unbound call), so the timer is armed at construction time instead - which
# also means it is armed before any of startup's own work begins.
_RealApp = QApplication


class _TimedApp(_RealApp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        QTimer.singleShot(7000, _inspect)


m.QApplication = _TimedApp

try:
    code = m.main()
finally:
    shutil.rmtree(SANDBOX, ignore_errors=True)

print("exit code        :", code)
for key in ("main_window", "visible", "maximized", "fullscreen",
            "fills_work_area", "covers_taskbar", "frameless",
            "size", "restore_size", "rows", "shortcuts", "theme"):
    print(f"{key:17}:", RESULT.get(key, "-- not reached --"))

checks = {
    "main window built": RESULT.get("main_window"),
    "visible": RESULT.get("visible"),
    "opens maximized": RESULT.get("maximized"),
    "not fullscreen / kiosk": RESULT.get("fullscreen") is False,
    "keeps its window frame": RESULT.get("frameless") is False,
    "fills the work area": RESULT.get("fills_work_area"),
    "leaves the taskbar visible": RESULT.get("covers_taskbar") is False,
    "has a sane restore size": bool(RESULT.get("restore_size", (0, 0))[0]),
}
print()
for name, passed in checks.items():
    print(f"  [{'OK' if passed else 'XX'}] {name}")

ok = all(checks.values())
print("\nSTARTUP:", "OK" if ok else "FAILED")
sys.exit(0 if ok else 1)

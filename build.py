"""Build a Windows executable with PyInstaller.

Usage (from the project root, inside the virtualenv):
    python build.py

Output: dist/UnifiedMailbox/UnifiedMailbox.exe
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ICON = ROOT / "assets" / "icon.ico"


def generate_icon() -> None:
    """Render the programmatic app icon to a .ico for the exe resource."""
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(
        [sys.argv[0], "-platform", "offscreen"]
    )
    from app.ui.icons import make_app_icon

    ICON.parent.mkdir(exist_ok=True)
    pixmap = make_app_icon(256).pixmap(256, 256)
    if not pixmap.save(str(ICON), "ICO"):
        raise RuntimeError("Could not write assets/icon.ico")
    del app


def build() -> int:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",                       # no console window
        "--name", "UnifiedMailbox",
        "--icon", str(ICON),
        # Google API client ships bundled discovery documents as data files.
        "--collect-data", "googleapiclient",
        # Keyring discovers its Windows backend at runtime.
        "--hidden-import", "keyring.backends.Windows",
        "--hidden-import", "win32ctypes.core",
        str(ROOT / "run.py"),
    ]
    print(" ".join(args))
    return subprocess.call(args, cwd=ROOT)


if __name__ == "__main__":
    generate_icon()
    code = build()
    if code == 0:
        exe = ROOT / "dist" / "UnifiedMailbox" / "UnifiedMailbox.exe"
        print(f"\nBuild OK: {exe}")
    sys.exit(code)

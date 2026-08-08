"""Build a Windows executable with PyInstaller.

Usage (from the project root, inside the virtualenv):
    python build.py

Output: dist/Unified/Unified.exe
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ICON = ROOT / "assets" / "icon.ico"


def generate_icon() -> None:
    """Build a proper multi-resolution .ico for the exe's Windows resource.

    A single 256px image saved with an .ico extension only ever contains
    that one size - Explorer/the taskbar then has to scale it down
    themselves for small contexts, which is exactly what makes app icons
    go blurry or vanish at 16-24px. Each size here is rendered by
    app.ui.icons at its own resolution (proportional stroke width, not a
    scaled-down large one) and assembled into one real multi-size .ico.
    """
    import io

    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(
        [sys.argv[0], "-platform", "offscreen"]
    )
    from app.ui.icons import ICON_SIZES, _draw_icon

    ICON.parent.mkdir(exist_ok=True)

    images = []
    for size in ICON_SIZES:
        pixmap = _draw_icon(size)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.ReadWrite)
        pixmap.save(buf, "PNG")
        images.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
        buf.close()

    largest = images[-1]
    largest.save(
        str(ICON), format="ICO",
        sizes=[(im.width, im.height) for im in images],
        append_images=images[:-1],
    )
    del app


def build() -> int:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",                       # no console window
        "--name", "Unified",
        "--icon", str(ICON),
        # Real SVG icon assets (app/ui/svg_icon.py resolves these relative
        # to its own frozen location, landing at _internal\assets\icons in
        # the onedir output) - without this the app crashes on first paint
        # with "Missing icon asset", since PyInstaller only bundles Python
        # code by default, never loose non-Python data files it can't see
        # referenced anywhere in the source.
        "--add-data", f"{ROOT / 'assets' / 'icons'}{os.pathsep}assets/icons",
        # Google API client ships bundled discovery documents as data files.
        "--collect-data", "googleapiclient",
        # Keyring discovers its Windows backend at runtime.
        "--hidden-import", "keyring.backends.Windows",
        "--hidden-import", "win32ctypes.core",
        # DPAPI (database encryption key) and its dependency chain.
        "--hidden-import", "win32crypt",
        "--hidden-import", "win32timezone",
        # cryptography's compiled backend is not always auto-detected.
        "--collect-all", "cryptography",
        str(ROOT / "run.py"),
    ]
    print(" ".join(args))
    return subprocess.call(args, cwd=ROOT)


if __name__ == "__main__":
    generate_icon()
    code = build()
    if code == 0:
        exe = ROOT / "dist" / "Unified" / "Unified.exe"
        print(f"\nBuild OK: {exe}")
    sys.exit(code)

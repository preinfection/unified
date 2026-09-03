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


def _gmail_discovery_document() -> Path:
    """The one Google API discovery document this app needs.

    Checked before the build so a missing or moved document fails here,
    loudly, instead of producing an executable that only fails the first
    time someone signs in to Gmail. What actually does the pruning is
    installer/pyinstaller_hooks/hook-googleapiclient.model.py.
    """
    import googleapiclient

    return (
        Path(googleapiclient.__file__).parent
        / "discovery_cache" / "documents" / "gmail.v1.json"
    )


def build() -> int:
    gmail_doc = _gmail_discovery_document()
    if not gmail_doc.exists():
        raise SystemExit(f"Gmail discovery document not found at {gmail_doc}")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name", "Unified",
        "--icon", str(ICON),
        # Real SVG icon assets (app/ui/svg_icon.py resolves these relative
        # to its own frozen location, landing at _internal\assets\icons in
        # the onedir output) - without this the app crashes on first paint
        # with "Missing icon asset", since PyInstaller only bundles Python
        # code by default, never loose non-Python data files it can't see
        # referenced anywhere in the source.
        "--add-data", f"{ROOT / 'assets' / 'icons'}{os.pathsep}assets/icons",
        # Only the Gmail discovery document is bundled - see
        # installer/pyinstaller_hooks/hook-googleapiclient.model.py, which
        # replaces PyInstaller's own hook for that module and drops the
        # other ~599 Google API documents (about 100 MB).
        "--additional-hooks-dir", str(ROOT / "installer" / "pyinstaller_hooks"),
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

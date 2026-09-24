"""Inspect the opening sequence frame by frame, without guessing.

Drives the REAL StartupWindow and OpeningBar through the same stage
strings app/main.py emits, grabbing a PNG at each step, and prints the
bar's fill at every stage so the progression can be checked as numbers
rather than eyeballed.

    python tools/startup_check.py            # dark
    python tools/startup_check.py --light
    python tools/startup_check.py --reduced  # reduced motion

Writes to tools/shots/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "tools" / "shots"


def main() -> int:
    light = "--light" in sys.argv
    reduced = "--reduced" in sys.argv

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from app.ui import motion, theme as t
    from app.ui.startup_window import StartupWindow
    from app.ui.style import get_stylesheet

    app = QApplication.instance() or QApplication([])
    if light:
        t.apply_mode("light")
    motion.set_motion_enabled(not reduced)
    app.setFont(t.make_font("field_value"))
    app.setStyleSheet(get_stylesheet())

    OUT.mkdir(parents=True, exist_ok=True)
    suffix = ("-light" if light else "") + ("-reduced" if reduced else "")

    def settle(ms: int) -> None:
        """Let real animation time pass - these are time-based tweens and
        processEvents alone would capture them at frame zero."""
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    win = StartupWindow()
    win.open_maximized()
    settle(60)

    print(f"{'stage':34} {'bar fill':>9}")
    print("-" * 46)
    print(f"{'(opened)':34} {win.bar.progress:>9.3f}")

    for stage in (
        "Checking install...",
        "Unlocking encrypted mailbox...",
        "Loading local cache...",
        "Preparing mailbox...",
    ):
        win.set_stage(stage)
        settle(420)
        print(f"{stage:34} {win.bar.progress:>9.3f}")

    win.grab().save(str(OUT / f"startup{suffix}.png"))
    print(f"\n  wrote tools/shots/startup{suffix}.png")

    # Read the fill from INSIDE the callback: the window carries
    # WA_DeleteOnClose, so by the time finish() hands back, the C++ widget
    # is gone and touching win.bar would read the Property descriptor off
    # the class rather than a value off the instance.
    final: list[float] = []
    win.finish(lambda: final.append(float(win.bar.progress)))
    settle(700)

    ok = bool(final) and final[0] == 1.0
    print(f"{'(finished)':34} {final[0] if final else float('nan'):>9.3f}")
    print("\nHANDOVER:", "OK" if ok else "FAILED - the shell would never appear")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""Design-review harness: render real app surfaces to PNG, offscreen.

Not a test. This exists because a UI cannot be reviewed by reading its
source: every visual decision in this app (spacing, rhythm, contrast,
hierarchy) is only checkable by looking at rendered pixels, and doing that
by launching the app by hand loses the seeded state that makes a surface
worth looking at in the first place.

    python tools/shoot.py [name ...]        # default: every surface
    python tools/shoot.py --light           # same surfaces, light mode

Writes PNGs to tools/shots/. Uses a throwaway tmp database seeded with
plausible mail, never the user's real Unified cache.
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile
from pathlib import Path

if "--offscreen" in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "tools" / "shots"

SENDERS = [
    ("Ada Lovelace", "ada@analytical.org"),
    ("Grace Hopper", "grace@navy.mil"),
    ("Margaret Hamilton", "mhamilton@draper.io"),
    ("Katherine Johnson", "kjohnson@nasa.gov"),
    ("Radia Perlman", "radia@spanning.net"),
    ("Barbara Liskov", "liskov@substitution.edu"),
    ("Karen Spärck Jones", "ksj@cam.ac.uk"),
    ("Sophie Wilson", "sophie@acorn.co.uk"),
]
SUBJECTS = [
    ("Re: the engine notes", "I have finished the appendix and it runs to three hundred pages, which is rather more than either of us expected when we started."),
    ("Compiler draft, second pass", "The linker is behaving now. I have attached the listing for the third block; the symbol table fix went in cleanly this morning."),
    ("Re: guidance computer priority display", "Agreed on the restart protocol. If the executive overflows we should drop the lowest priority job rather than halt, and the display should say so plainly."),
    ("Trajectory verification for the November window", "The numbers check out to nine places. I would still like a second pass on the re-entry corridor before anyone signs anything."),
    ("Spanning tree: the algorithm, and the poem", "Enclosed is the note on loop-free topology. The poem is not load-bearing but the network is."),
    ("On subtypes and substitution", "If S is a subtype of T then objects of type T may be replaced with objects of type S without altering correctness. That is the whole of it."),
    ("Term weighting and why it works", "Inverse document frequency is doing the work here, not the term counts. The retrieval results in section four make that fairly clear."),
    ("ARM instruction set, final review", "Fewer instructions, all of them one cycle. The whole design fits on the whiteboard and I think that is the point."),
]


def seed(db_path: Path):
    from app.database import Database
    db = Database(db_path)
    a1 = db.add_account("ada@analytical.org", "gmail")
    a2 = db.add_account("work@company.com", "imap", imap_host="mail.company.com",
                        smtp_host="smtp.company.com")
    a3 = db.add_account("archive@personal.net", "imap", imap_host="imap.personal.net",
                        smtp_host="smtp.personal.net")
    import time
    now = int(time.time())
    rows = []
    for i in range(60):
        name, addr = SENDERS[i % len(SENDERS)]
        subj, snip = SUBJECTS[i % len(SUBJECTS)]
        aid = (a1, a2, a3)[i % 3]
        # spread across today / yesterday / earlier so the date groups show
        ts = now - (i * 3200 if i < 8 else 86400 + i * 5000)
        rows.append(dict(
            account_id=aid, uid=f"u{i}", folder="inbox",
            sender_name=name, sender_email=addr,
            subject=subj, snippet=snip,
            body_text=snip + "\n\n" + snip, body_html="",
            date_ts=ts, is_read=0 if i % 3 == 0 else 1,
            is_starred=1 if i % 7 == 0 else 0,
            has_attachments=1 if i % 5 == 0 else 0, body_fetched=1,
        ))
    db.upsert_emails(rows)
    return db, a1


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    light = "--light" in sys.argv

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from app.ui import theme as t
    from app.ui.style import get_stylesheet

    app = QApplication.instance() or QApplication([])
    if light:
        t.apply_mode("light")
    app.setFont(t.make_font("field_value"))
    app.setStyleSheet(get_stylesheet())

    tmp = Path(tempfile.mkdtemp(prefix="unified-shot-"))
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = "-light" if light else ""

    try:
        from app import config
        from app.services import sync_service

        # No network, ever: stub the sync worker before MainWindow builds.
        class _NoSync(sync_service.QThread):
            progress = sync_service.Signal(int, str, int, int)
            result_ready = sync_service.Signal(int, dict)

            def __init__(self, db_path, account_id, parent=None):
                super().__init__(parent)

            def request_stop(self): pass
            def start(self): pass

        sync_service.AccountSyncWorker = _NoSync

        db, a1 = seed(tmp / "mailbox.db")
        settings = config.Settings(tmp / "settings.json")
        # Through the real setting, not by calling apply_mode() behind the
        # window's back: MainWindow binds the palette from Settings as it
        # builds, so a shot taken the other way would be testing a code
        # path the app does not use.
        settings.set("theme_mode", "light" if light else "dark")

        from app.ui.main_window import MainWindow
        win = MainWindow(db, settings)
        win.resize(1440, 900)
        win.show()
        app.processEvents()

        shots = {}

        def settle(ms=120):
            """Let the event loop actually run before grabbing.

            processEvents() alone is not enough and the difference is not
            cosmetic: QWidget.grab() calls render(), which paints children
            Qt has not finished deciding about yet. Reviewing a shot taken
            that way showed a full-height scrollbar down the compose body
            that the running application does not have - the widget hides
            it once layout settles - and a review that cannot tell a real
            defect from a capture artifact is worse than no review.
            """
            loop = QEventLoop()
            QTimer.singleShot(ms, loop.quit)
            loop.exec()

        def shoot(name, widget, w=1440, h=900):
            if args and name not in args:
                return
            widget.resize(w, h)
            # SHOWN, THEN SETTLED, THEN GRABBED - and the show() is the
            # part that matters. grab() calls render(), which paints
            # children whose visibility Qt has never resolved, so grabbing
            # a dialog that was never shown drew a full-height scrollbar
            # down the compose body that the real window does not have.
            # Half an hour went into "fixing" that phantom before the
            # widget was asked directly and reported max=0, hidden.
            if not widget.isVisible():
                widget.show()
            widget.resize(w, h)
            settle()
            path = OUT / f"{name}{suffix}.png"
            widget.grab().save(str(path))
            print(f"  {path.relative_to(ROOT)}")

        print("rendering:")
        # 1. the shell with a message open
        first = win.email_list._model._rows
        mid = next(r for r in first if not r.get("is_header"))
        win.email_list.select_email(mid["id"])
        app.processEvents()
        shoot("shell", win)

        # 2. narrow window
        shoot("shell-narrow", win, 1000, 720)
        win.resize(1440, 900)
        app.processEvents()

        # 2b. scrolled, so the softened scroll boundaries are visible
        _bar = win.email_list.verticalScrollBar()
        _bar.setValue(_bar.maximum() // 2)
        app.processEvents()
        shoot("shell-scrolled", win)
        _bar.setValue(_bar.minimum())
        app.processEvents()

        # 3. collapsed sidebar (no animation - a shot wants the end state)
        win.sidebar.set_collapsed(True, animate=False)
        app.processEvents()
        shoot("shell-collapsed", win)
        win.sidebar.set_collapsed(False, animate=False)
        app.processEvents()

        # 4. empty search result
        win.toolbar.search_edit.setText("zzzznothingmatches")
        win._run_search()
        app.processEvents()
        shoot("empty-search", win)
        win.toolbar.search_edit.setText("")
        win._run_search()
        app.processEvents()

        # 5. deliberately awkward data - the layout has to degrade, not break
        import time as _t
        _now = int(_t.time())
        db.upsert_emails([
            dict(account_id=a1, uid="awk-1", folder="inbox",
                 sender_name="Bartholomew Fitzwilliam-Cholmondeley de la Rochefoucauld III",
                 sender_email="bartholomew@an-extremely-long-domain-name.example",
                 subject=("Re: Fwd: Re: quarterly consolidated reconciliation of the "
                          "distributed ledger subsystem and its downstream dependencies"),
                 snippet="x " * 120, body_text="body", body_html="",
                 date_ts=_now - 10, is_read=0, is_starred=1,
                 has_attachments=1, body_fetched=1),
            dict(account_id=a1, uid="awk-2", folder="inbox",
                 sender_name="", sender_email="", subject="", snippet="",
                 body_text="", body_html="", date_ts=_now - 20, is_read=1,
                 is_starred=0, has_attachments=0, body_fetched=1),
            dict(account_id=a1, uid="awk-3", folder="inbox",
                 sender_name="日本語の送信者名前",
                 sender_email="test@example.jp",
                 subject="件名のテスト - こんにちは世界",
                 snippet="これはスニペットです。",
                 body_text="body", body_html="", date_ts=_now - 30, is_read=0,
                 is_starred=1, has_attachments=1, body_fetched=1),
        ])
        win.reload_email_list()
        app.processEvents()
        awk = win.email_list._model.index_of(
            next(r["id"] for r in win.email_list._model._rows
                 if not r.get("is_header") and r.get("uid") == "awk-1")
        )
        if awk.isValid():
            win.email_list.setCurrentIndex(awk)
        app.processEvents()
        shoot("awkward", win)
        shoot("awkward-narrow", win, 1000, 720)
        win.resize(1440, 900)
        app.processEvents()

        # 6. compose
        from app.ui.compose_dialog import ComposeDialog
        cd = ComposeDialog(db.get_accounts(), win)
        cd.to_edit.setText("grace@navy.mil")
        cd.subject_edit.setText("Re: compiler draft, second pass")
        cd.body_edit.setPlainText(
            "The linker is behaving now.\n\n"
            "I have attached the listing for the third block; the symbol\n"
            "table fix went in cleanly this morning."
        )
        cd.resize(720, 560)
        app.processEvents()
        shoot("compose", cd, 720, 560)

        # 5. settings
        from app.ui.settings_dialog import SettingsDialog
        sd = SettingsDialog(settings, win.manager, win)
        sd.resize(820, 600)
        app.processEvents()
        shoot("settings", sd, 820, 600)
        sd._rail_group.buttons()[1].click()
        app.processEvents()
        shoot("settings-appearance", sd, 820, 600)

        win.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

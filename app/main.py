"""Application entry point.

Run from the project root with:  python -m app.main   (or: python run.py)
Do NOT run "python app/main.py" - that puts app/ itself on sys.path, where
the app.email package would shadow the standard library's email module.

Startup sequence: a StartupWindow appears the instant QApplication exists
(no dependency on the database or settings), while the real init work -
legacy-install migration, decrypting the local mailbox cache, opening the
database - runs on a background _InitWorker thread. The UI thread is never
blocked by any of it; previously all three ran synchronously before the
first window ever appeared, which is what made the app look frozen at
launch on anything but a tiny, freshly-decrypted cache.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, __version__, config, logging_setup
from app.database import Database
from app.migration import migrate_legacy_install
from app.security import crypto_store
from app.ui.main_window import MainWindow
from app.ui.startup_window import StartupWindow
from app.ui.style import get_stylesheet

log = logging.getLogger(__name__)


class _InitWorker(QThread):
    """Runs every startup step that doesn't touch a Qt widget off the UI
    thread: legacy migration, mailbox decrypt, database open/migrate.
    stage() reports real, already-completed steps - never a guess at how
    long the next one will take.
    """

    stage = Signal(str)
    ready = Signal(object, object, bool, object)  # db, settings, recovered, unlock_error
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.stage.emit("Checking install...")
            migrate_legacy_install()

            self.stage.emit("Unlocking encrypted mailbox...")
            data_dir = config.app_data_dir()
            recovered, unlock_error = crypto_store.unlock_database(data_dir)

            self.stage.emit("Loading local cache...")
            settings = config.Settings()
            db = Database(config.db_path())

            self.ready.emit(db, settings, recovered, unlock_error)
        except Exception as e:
            log.exception("Startup failed")
            self.failed.emit(str(e))


def main() -> int:
    logging_setup.setup_logging()
    log.info("Starting %s v%s", APP_NAME, __version__)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")  # consistent base look across Windows versions
    app.setStyleSheet(get_stylesheet())
    app.setQuitOnLastWindowClosed(True)

    # Visible immediately - nothing above this line touches the database,
    # settings, or the encrypted cache, so there is nothing left to make
    # the app look like it hasn't started.
    startup = StartupWindow()
    startup.show()

    # Keeps MainWindow (built once init finishes) reachable after this
    # function's local scope would otherwise let it go out of scope, and
    # gives closeEvent something to flush/checkpoint after app.exec() ends.
    state: dict[str, object] = {}

    def on_stage(text: str) -> None:
        startup.set_stage(text)

    def on_ready(db, settings, recovered: bool, unlock_error) -> None:
        startup.set_stage("Preparing mailbox...")
        window = MainWindow(db, settings)
        state["window"] = window
        window.show()
        startup.close()

        if unlock_error:
            QMessageBox.warning(
                window,
                "Encrypted mailbox could not be unlocked",
                "Your local mailbox is encrypted and could not be unlocked on "
                "this machine or user account "
                f"({unlock_error}).\n\n"
                "The encrypted file was preserved rather than overwritten. "
                "Unified will start with an empty local cache - remove and "
                "re-add your accounts to rebuild it, or restore the original "
                "key.bin from a backup of this machine to try again.",
            )
        elif recovered:
            window.statusBar().showMessage(
                "Recovered mailbox after an interrupted session - no data lost"
            )

    def on_failed(message: str) -> None:
        startup.close()
        QMessageBox.critical(
            None, f"{APP_NAME} could not start",
            f"Something went wrong while starting {APP_NAME}:\n\n{message}",
        )
        app.quit()

    worker = _InitWorker()
    worker.stage.connect(on_stage)
    worker.ready.connect(on_ready)
    worker.failed.connect(on_failed)
    worker.start()

    code = app.exec()

    window = state.get("window")
    if window is not None:
        # WAL must be flushed into mailbox.db before encrypting it, or the
        # encrypted snapshot could miss the most recent writes.
        window.db.checkpoint_and_close()
        crypto_store.lock_database(config.app_data_dir())
    log.info("Exited with code %s", code)
    return code


if __name__ == "__main__":
    sys.exit(main())

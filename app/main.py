"""Application entry point.

Run from the project root with:  python -m app.main   (or: python run.py)
Do NOT run "python app/main.py" - that puts app/ itself on sys.path, where
the app.email package would shadow the standard library's email module.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, __version__, config, logging_setup
from app.database import Database
from app.migration import migrate_legacy_install
from app.security import crypto_store
from app.ui.main_window import MainWindow
from app.ui.style import get_stylesheet

log = logging.getLogger(__name__)


def main() -> int:
    logging_setup.setup_logging()
    log.info("Starting %s v%s", APP_NAME, __version__)
    migrate_legacy_install()

    data_dir = config.app_data_dir()
    recovered, unlock_error = crypto_store.unlock_database(data_dir)
    if recovered:
        log.warning("Recovered mailbox from an interrupted previous session")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")  # consistent base look across Windows versions
    app.setStyleSheet(get_stylesheet())
    app.setQuitOnLastWindowClosed(True)

    settings = config.Settings()
    db = Database(config.db_path())

    window = MainWindow(db, settings)
    window.show()

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

    code = app.exec()
    # WAL must be flushed into mailbox.db before encrypting it, or the
    # encrypted snapshot could miss the most recent writes.
    db.checkpoint_and_close()
    crypto_store.lock_database(data_dir)
    log.info("Exited with code %s", code)
    return code


if __name__ == "__main__":
    sys.exit(main())

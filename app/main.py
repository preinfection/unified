"""Application entry point.

Run from the project root with:  python -m app.main   (or: python run.py)
Do NOT run "python app/main.py" - that puts app/ itself on sys.path, where
the app.email package would shadow the standard library's email module.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from app import APP_NAME, config, logging_setup
from app.database import Database
from app.migration import migrate_legacy_install
from app.ui.main_window import MainWindow
from app.ui.style import STYLESHEET

log = logging.getLogger(__name__)


def main() -> int:
    logging_setup.setup_logging()
    log.info("Starting %s", APP_NAME)
    migrate_legacy_install()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")  # consistent base look across Windows versions
    app.setStyleSheet(STYLESHEET)
    app.setQuitOnLastWindowClosed(True)

    settings = config.Settings()
    db = Database(config.db_path())

    window = MainWindow(db, settings)
    window.show()

    code = app.exec()
    db.close()
    log.info("Exited with code %s", code)
    return code


if __name__ == "__main__":
    sys.exit(main())

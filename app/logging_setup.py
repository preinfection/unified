"""Central logging configuration: rotating file log plus console output."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from app import config


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:  # already configured (e.g. in tests)
        return
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.handlers.RotatingFileHandler(
        config.log_dir() / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    root.addHandler(console)

    # Third-party libraries are noisy at INFO level.
    for noisy in ("googleapiclient", "google", "urllib3", "google_auth_httplib2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

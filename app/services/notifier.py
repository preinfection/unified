"""Desktop notifications via the system tray icon."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QSystemTrayIcon

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, tray: QSystemTrayIcon, settings):
        self.tray = tray
        self.settings = settings

    def notify_new_mail(self, count: int) -> None:
        if count <= 0 or not self.settings.get("notifications_enabled"):
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info("System tray unavailable; skipping notification")
            return
        plural = "s" if count != 1 else ""
        self.tray.showMessage(
            "UnifiedMailbox",
            f"{count} new email{plural} received",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

"""Add/remove accounts, coordinating the database and secret storage."""

from __future__ import annotations

import logging

from app.auth import gmail_oauth, secrets_store
from app.database import Database
from app.email import imap_client

log = logging.getLogger(__name__)


class AccountError(Exception):
    pass


class AccountManager:
    def __init__(self, db: Database):
        self.db = db

    # --------------------------------------------------------------------- gmail

    def add_gmail_account(self) -> dict:
        """Run the OAuth consent flow and register the account.

        Blocking (opens a browser and waits) - call from a worker thread.
        """
        from app.email.gmail_client import GmailClient

        creds = gmail_oauth.run_oauth_flow()
        email_addr = GmailClient.profile_email(creds)
        if self.db.get_account_by_email(email_addr):
            gmail_oauth.save_token(email_addr, creds)  # refresh stored token anyway
            raise AccountError(f"{email_addr} is already added.")
        gmail_oauth.save_token(email_addr, creds)
        account_id = self.db.add_account(email=email_addr, provider="gmail")
        log.info("Added Gmail account %s (id=%s)", email_addr, account_id)
        return self.db.get_account(account_id)

    # ---------------------------------------------------------------------- imap

    def add_imap_account(
        self,
        email_addr: str,
        password: str,
        imap_host: str,
        imap_port: int,
        smtp_host: str,
        smtp_port: int,
        display_name: str = "",
    ) -> dict:
        """Verify the IMAP login, then store the password in the OS keyring."""
        email_addr = email_addr.strip().lower()
        if self.db.get_account_by_email(email_addr):
            raise AccountError(f"{email_addr} is already added.")
        imap_client.verify_login(email_addr, password, imap_host, imap_port)
        secrets_store.set_secret(
            secrets_store.KIND_IMAP_PASSWORD, email_addr, password
        )
        account_id = self.db.add_account(
            email=email_addr,
            provider="imap",
            display_name=display_name,
            imap_host=imap_host,
            imap_port=imap_port,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
        )
        log.info("Added IMAP account %s (id=%s)", email_addr, account_id)
        return self.db.get_account(account_id)

    # -------------------------------------------------------------------- remove

    def remove_account(self, account_id: int) -> None:
        account = self.db.get_account(account_id)
        if not account:
            return
        if account["provider"] == "gmail":
            gmail_oauth.remove_token(account["email"])
        else:
            secrets_store.delete_secret(
                secrets_store.KIND_IMAP_PASSWORD, account["email"]
            )
        self.db.remove_account(account_id)
        log.info("Removed account %s", account["email"])

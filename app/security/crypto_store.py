"""At-rest encryption for the local mailbox cache.

Threat model - what this actually protects against:
  - A stolen or discarded machine/disk, or a copy of %APPDATA% that ends up
    in a cloud backup, USB drive, or a different computer: the database is
    unreadable without the DPAPI-wrapped key, which only unwraps under the
    same Windows user account on the same machine (the same mechanism
    Chrome/Edge use to protect saved passwords and cookies).
  - Another Windows account on a shared machine reading this user's files.
  - Casual inspection of the AppData folder while the app is not running.

What this does NOT protect against (stated plainly - no product can):
  - Malware or an attacker with full control of the *already logged-in*
    user's active session while Unified is running: at that point the OS
    itself will hand over the same DPAPI-unwrapped key to anything running
    as that user, exactly as it would for the browser's saved passwords.
    No local, prompt-free encryption scheme can defend against that,
    because the app must be able to decrypt without asking for a password
    every launch.

Design: the database is only ever plaintext on disk while the app is
running. On clean shutdown it is encrypted to mailbox.db.enc (AES-256-GCM)
and the plaintext copy is overwritten and deleted. On the next launch, the
.enc file is decrypted back to a working plaintext copy. If the app is
killed or crashes, the plaintext copy from that session may remain until
the next clean exit - see migration/startup handling in main.py.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)

_KEY_FILE = "key.bin"
_NONCE_LEN = 12  # standard for AES-GCM
_AAD = b"unified-mailbox-db-v1"  # binds ciphertext to this format/purpose


class CryptoError(Exception):
    pass


def _dpapi_protect(data: bytes, description: str) -> bytes:
    import win32crypt

    blob = win32crypt.CryptProtectData(data, description, None, None, None, 0)
    return bytes(blob)


def _dpapi_unprotect(blob: bytes) -> bytes:
    import win32crypt

    _description, data = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return bytes(data)


def get_or_create_master_key(app_data_dir: Path) -> bytes:
    """Return this install's 32-byte AES key, generating and DPAPI-wrapping
    one on first use. The wrapped key file is useless outside this Windows
    user account and machine - DPAPI itself enforces that, not this code."""
    key_path = app_data_dir / _KEY_FILE
    if key_path.exists():
        try:
            wrapped = key_path.read_bytes()
            key = _dpapi_unprotect(wrapped)
            if len(key) == 32:
                return key
            log.error("Stored master key has unexpected length; regenerating")
        except Exception as e:
            log.error("Could not unwrap stored master key (%s); regenerating. "
                      "Any previously encrypted database becomes unreadable "
                      "and will be treated as empty.", e)

    key = os.urandom(32)
    wrapped = _dpapi_protect(key, "Unified mailbox encryption key")
    tmp_path = key_path.with_suffix(".tmp")
    tmp_path.write_bytes(wrapped)
    os.replace(tmp_path, key_path)
    return key


def encrypt_file(src: Path, dest: Path, key: bytes) -> None:
    """Encrypt src to dest (AES-256-GCM, random nonce per call)."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_LEN)
    plaintext = src.read_bytes()
    ciphertext = aesgcm.encrypt(nonce, plaintext, _AAD)
    tmp_path = dest.with_suffix(dest.suffix + ".tmp")
    tmp_path.write_bytes(nonce + ciphertext)
    os.replace(tmp_path, dest)  # atomic on the same volume


def decrypt_file(src: Path, dest: Path, key: bytes) -> None:
    """Decrypt src to dest. Raises CryptoError on a wrong key or tampering."""
    aesgcm = AESGCM(key)
    raw = src.read_bytes()
    nonce, ciphertext = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, _AAD)
    except InvalidTag as e:
        raise CryptoError(
            "Encrypted database could not be verified (wrong key or the "
            "file was modified)"
        ) from e
    tmp_path = dest.with_suffix(dest.suffix + ".tmp")
    tmp_path.write_bytes(plaintext)
    os.replace(tmp_path, dest)


def secure_delete(path: Path) -> None:
    """Best-effort overwrite-then-delete of a plaintext file.

    Not a guarantee on SSDs/journaling filesystems (wear-leveling and
    filesystem journals can retain copies) - it is meaningfully better than
    a plain delete against casual recovery, not a forensic-grade wipe.
    """
    try:
        size = path.stat().st_size
        with open(path, "r+b") as f:
            f.write(b"\x00" * size)
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        log.warning("Could not overwrite %s before delete: %s", path, e)
    try:
        path.unlink()
    except OSError as e:
        log.error("Could not delete %s: %s", path, e)


def lock_database(app_data_dir: Path) -> None:
    """Encrypt the working database on clean shutdown and remove the
    plaintext copy. Never raises - a failure here must not block exit or
    risk the user's data; it just leaves the plaintext copy in place."""
    plain = app_data_dir / "mailbox.db"
    if not plain.exists():
        return
    enc = app_data_dir / "mailbox.db.enc"
    try:
        key = get_or_create_master_key(app_data_dir)
        encrypt_file(plain, enc, key)
        secure_delete(plain)
        for wal_suffix in ("-wal", "-shm"):  # SQLite WAL side files
            side = app_data_dir / f"mailbox.db{wal_suffix}"
            if side.exists():
                secure_delete(side)
        log.info("Database encrypted at rest")
    except Exception as e:
        log.error("Could not encrypt database on exit (%s); it remains "
                  "readable in plaintext until the next successful save", e)


def unlock_database(app_data_dir: Path) -> tuple[bool, Optional[str]]:
    """Prepare the working plaintext database for this session.

    Returns (recovered_from_interruption, error):
      - If a plaintext mailbox.db already exists, a previous session ended
        without encrypting it (killed/crashed rather than closed normally).
        That copy is the newest data available, so it is left exactly as
        is - never overwritten by decrypting an older .enc snapshot over
        it. `recovered_from_interruption` is True only when an .enc file
        also exists, meaning this isn't just a first run.
      - Otherwise, if mailbox.db.enc exists, it is decrypted to mailbox.db.
      - If decryption fails (wrong key, moved machine, corrupted file), the
        undecryptable file is preserved under a .locked-<timestamp> name
        rather than touched further, so a later clean exit cannot encrypt
        a fresh empty database over it and destroy the only copy. The
        error is returned so the caller can tell the user plainly instead
        of silently starting an empty mailbox.
      - Never raises.
    """
    plain = app_data_dir / "mailbox.db"
    enc = app_data_dir / "mailbox.db.enc"

    if plain.exists():
        return enc.exists(), None

    if not enc.exists():
        return False, None  # fresh install: nothing to unlock yet

    try:
        key = get_or_create_master_key(app_data_dir)
        decrypt_file(enc, plain, key)
        log.info("Database decrypted for this session")
        return False, None
    except Exception as e:
        log.error("Could not decrypt database: %s", e)
        backup_name = f"mailbox.db.enc.locked-{int(time.time())}"
        try:
            os.replace(enc, app_data_dir / backup_name)
            log.warning("Preserved the undecryptable file as %s so it is "
                       "never overwritten", backup_name)
        except OSError as move_err:
            log.error("Could not preserve undecryptable file: %s", move_err)
        return False, str(e)

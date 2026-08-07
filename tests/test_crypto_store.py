"""Tests for at-rest database encryption (DPAPI-wrapped AES-256-GCM).

Uses the real Windows DPAPI (no mocking needed - it only touches files
under tmp_path, and does not write anywhere persistent like the keyring).
"""

import pytest

from app.security import crypto_store


@pytest.fixture()
def data_dir(tmp_path):
    return tmp_path


def test_master_key_is_32_bytes_and_persists(data_dir):
    key1 = crypto_store.get_or_create_master_key(data_dir)
    assert len(key1) == 32
    assert (data_dir / "key.bin").exists()

    key2 = crypto_store.get_or_create_master_key(data_dir)
    assert key1 == key2  # same key reloaded, not regenerated


def test_key_file_is_not_the_raw_key(data_dir):
    """The on-disk key file must be DPAPI-wrapped, not the bare key."""
    key = crypto_store.get_or_create_master_key(data_dir)
    on_disk = (data_dir / "key.bin").read_bytes()
    assert key not in on_disk
    assert on_disk != key


def test_corrupted_key_file_regenerates_instead_of_crashing(data_dir):
    crypto_store.get_or_create_master_key(data_dir)
    (data_dir / "key.bin").write_bytes(b"not a valid dpapi blob")
    key = crypto_store.get_or_create_master_key(data_dir)  # must not raise
    assert len(key) == 32


def test_encrypt_decrypt_roundtrip(tmp_path):
    key = crypto_store.get_or_create_master_key(tmp_path)
    src = tmp_path / "plain.bin"
    src.write_bytes(b"sensitive email content \x00\x01\x02" * 100)
    enc = tmp_path / "plain.bin.enc"
    crypto_store.encrypt_file(src, enc, key)
    assert enc.exists()
    assert enc.read_bytes() != src.read_bytes()

    out = tmp_path / "restored.bin"
    crypto_store.decrypt_file(enc, out, key)
    assert out.read_bytes() == src.read_bytes()


def test_tampered_ciphertext_is_rejected(tmp_path):
    key = crypto_store.get_or_create_master_key(tmp_path)
    src = tmp_path / "plain.bin"
    src.write_bytes(b"original content")
    enc = tmp_path / "plain.bin.enc"
    crypto_store.encrypt_file(src, enc, key)

    data = bytearray(enc.read_bytes())
    data[-1] ^= 0xFF  # flip a bit in the ciphertext/tag
    enc.write_bytes(bytes(data))

    with pytest.raises(crypto_store.CryptoError):
        crypto_store.decrypt_file(enc, tmp_path / "out.bin", key)


def test_wrong_key_is_rejected(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    key_a = crypto_store.get_or_create_master_key(tmp_path / "a")
    key_b = crypto_store.get_or_create_master_key(tmp_path / "b")
    src = tmp_path / "a" / "plain.bin"
    src.write_bytes(b"secret")
    enc = tmp_path / "a" / "plain.bin.enc"
    crypto_store.encrypt_file(src, enc, key_a)

    with pytest.raises(crypto_store.CryptoError):
        crypto_store.decrypt_file(enc, tmp_path / "out.bin", key_b)


def test_secure_delete_removes_file(tmp_path):
    f = tmp_path / "secret.db"
    f.write_bytes(b"data")
    crypto_store.secure_delete(f)
    assert not f.exists()


# --------------------------------------------------------- lock/unlock cycle


def test_unlock_on_fresh_install_is_noop(data_dir):
    recovered, error = crypto_store.unlock_database(data_dir)
    assert recovered is False
    assert error is None
    assert not (data_dir / "mailbox.db").exists()


def test_lock_then_unlock_roundtrip(data_dir):
    db_path = data_dir / "mailbox.db"
    db_path.write_bytes(b"fake sqlite content")

    crypto_store.lock_database(data_dir)
    assert not db_path.exists()
    assert (data_dir / "mailbox.db.enc").exists()

    recovered, error = crypto_store.unlock_database(data_dir)
    assert recovered is False
    assert error is None
    assert db_path.read_bytes() == b"fake sqlite content"


def test_crash_leftover_plaintext_is_never_overwritten(data_dir):
    """The core safety property: a crash must never lose data to a stale
    encrypted snapshot being decrypted back over the newer plaintext."""
    db_path = data_dir / "mailbox.db"
    db_path.write_bytes(b"session 1 data")
    crypto_store.lock_database(data_dir)  # -> mailbox.db.enc holds "session 1"

    recovered, error = crypto_store.unlock_database(data_dir)
    assert recovered is False and error is None
    db_path.write_bytes(b"session 2 data - newer")  # simulate continued work

    # Process is killed here - no lock_database() call happens.

    recovered, error = crypto_store.unlock_database(data_dir)
    assert recovered is True  # an .enc exists, so this really is a recovery
    assert error is None
    assert db_path.read_bytes() == b"session 2 data - newer"  # untouched


def test_undecryptable_file_is_preserved_not_lost(data_dir):
    db_path = data_dir / "mailbox.db"
    db_path.write_bytes(b"data")
    crypto_store.lock_database(data_dir)

    # Simulate moving to a different machine: wipe the key so it can never
    # unwrap this .enc file again (mirrors "wrong/missing key" in general).
    (data_dir / "key.bin").unlink()
    crypto_store.get_or_create_master_key(data_dir)  # different key now

    recovered, error = crypto_store.unlock_database(data_dir)
    assert error is not None
    assert not (data_dir / "mailbox.db.enc").exists()  # moved, not deleted
    locked_backups = list(data_dir.glob("mailbox.db.enc.locked-*"))
    assert len(locked_backups) == 1
    assert not db_path.exists()  # never fabricated an empty plaintext file


def test_second_unlock_after_failure_does_not_destroy_backup(data_dir):
    """A later clean exit must not encrypt a fresh empty db over the
    preserved-but-undecryptable backup from an earlier failure."""
    db_path = data_dir / "mailbox.db"
    db_path.write_bytes(b"data")
    crypto_store.lock_database(data_dir)
    (data_dir / "key.bin").unlink()
    crypto_store.get_or_create_master_key(data_dir)
    crypto_store.unlock_database(data_dir)  # creates the .locked-* backup
    backup = next(data_dir.glob("mailbox.db.enc.locked-*"))
    backup_contents = backup.read_bytes()

    # App proceeds with a fresh, empty database this session, then exits
    # cleanly - this must produce a new mailbox.db.enc, not touch the backup.
    db_path.write_bytes(b"")
    crypto_store.lock_database(data_dir)

    assert backup.read_bytes() == backup_contents
    assert (data_dir / "mailbox.db.enc").exists()

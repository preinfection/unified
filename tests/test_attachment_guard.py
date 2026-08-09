"""Tests for the attachment hardening layer.

This is filename/type/size hardening, NOT antivirus - see the module
docstring in app/security/attachment_guard.py. These tests cover the
attacks that hardening is actually supposed to stop.
"""
from __future__ import annotations

import pytest

from app.security.attachment_guard import (
    MAX_ATTACHMENT_BYTES,
    Verdict,
    check_attachment,
    is_archive_member_safe,
    safe_destination,
    sanitize_filename,
)


# ------------------------------------------------------ path traversal

@pytest.mark.parametrize("hostile", [
    "../../../../Windows/System32/drivers/etc/hosts",
    r"..\..\..\Users\Public\Startup\evil.txt",
    "/etc/passwd",
    r"C:\Windows\System32\config\SAM",
    r"\\attacker\share\payload",
    "....//....//evil",
    "subdir/nested/file.pdf",
])
def test_filenames_never_retain_a_path(hostile):
    safe = sanitize_filename(hostile)
    assert "/" not in safe and "\\" not in safe
    assert not safe.startswith("..")
    assert ":" not in safe


def test_pure_traversal_segments_fall_back_to_a_generic_name():
    for name in ("..", ".", "", None, "   ", "/", "\\"):
        assert sanitize_filename(name) == "attachment"


def test_safe_destination_refuses_to_escape_the_target_directory(tmp_path):
    inside = safe_destination(tmp_path, "report.pdf")
    assert inside.parent == tmp_path.resolve()
    # Traversal is neutralised by sanitisation, so it lands inside.
    assert safe_destination(tmp_path, "../../evil.pdf").parent == tmp_path.resolve()


def test_safe_destination_rejects_a_directory_escape_it_cannot_sanitise(tmp_path, monkeypatch):
    """If sanitisation is ever weakened, the resolved-path containment
    check must still be the thing that stops the write."""
    import app.security.attachment_guard as guard
    monkeypatch.setattr(guard, "sanitize_filename", lambda n: n)  # defeat step 1
    with pytest.raises(ValueError):
        guard.safe_destination(tmp_path, "../escaped.txt")


# ------------------------------------------------- zip-slip in archives

@pytest.mark.parametrize("member", [
    "../evil.sh",
    "../../etc/cron.d/x",
    "/absolute/evil",
    r"..\..\Windows\evil.dll",
    r"C:\evil.exe",
    "nested/../../escape",
])
def test_archive_members_that_escape_are_refused(member):
    assert is_archive_member_safe(member) is False


@pytest.mark.parametrize("member", [
    "readme.txt",
    "docs/manual.pdf",
    "images/logo.png",
])
def test_ordinary_archive_members_are_allowed(member):
    assert is_archive_member_safe(member) is True


# ------------------------------------------- Windows filename weirdness

@pytest.mark.parametrize("reserved", ["CON", "con.txt", "PRN.pdf", "aux", "COM1.doc", "LPT9"])
def test_windows_reserved_device_names_are_defused(reserved):
    safe = sanitize_filename(reserved)
    stem = safe.partition(".")[0].lower()
    assert stem not in ("con", "prn", "aux", "nul", "com1", "lpt9")


def test_trailing_dot_and_space_tricks_are_stripped():
    """Windows silently drops these, so "evil.exe." would otherwise be
    checked as a harmless name and land on disk as an executable."""
    assert sanitize_filename("evil.exe.") == "evil.exe"
    assert sanitize_filename("evil.exe   ") == "evil.exe"
    # And the stripped form is still correctly refused.
    assert check_attachment("evil.exe.").verdict is Verdict.BLOCK


def test_control_characters_and_nul_are_removed():
    safe = sanitize_filename("re\x00port\x1f\x7f.pdf")
    assert "\x00" not in safe and "\x1f" not in safe and "\x7f" not in safe


def test_right_to_left_override_disguise_is_defeated():
    """"invoice<U+202E>gnp.exe" renders as "invoicexe.png" in a file
    listing while actually being an .exe."""
    disguised = "invoice\u202egnp.exe"
    safe = sanitize_filename(disguised)
    assert "\u202e" not in safe
    assert safe.endswith(".exe")
    assert check_attachment(disguised).verdict is Verdict.BLOCK


def test_absurdly_long_names_are_truncated_but_keep_their_extension():
    safe = sanitize_filename("A" * 5000 + ".pdf")
    assert len(safe) <= 120
    assert safe.endswith(".pdf")


# --------------------------------------------------- dangerous content

@pytest.mark.parametrize("name", [
    "invoice.exe", "setup.msi", "run.bat", "x.cmd", "s.vbs", "a.js",
    "p.ps1", "m.scr", "l.lnk", "h.hta", "r.reg", "j.jar", "d.dll", "k.sh",
])
def test_executable_and_script_attachments_are_blocked(name):
    assert check_attachment(name).verdict is Verdict.BLOCK


@pytest.mark.parametrize("name", [
    "invoice.pdf.exe", "photo.jpg.scr", "report.docx.js", "archive.zip.bat",
])
def test_disguised_double_extensions_are_blocked(name):
    check = check_attachment(name)
    assert check.verdict is Verdict.BLOCK
    assert "isguised" in check.reason


def test_executable_content_type_is_blocked_even_with_a_harmless_name():
    check = check_attachment("totally_fine.pdf", "application/x-msdownload")
    assert check.verdict is Verdict.BLOCK


@pytest.mark.parametrize("name", ["backup.zip", "book.rar", "sheet.xlsm", "disk.iso"])
def test_archives_and_macro_documents_warn_rather_than_block(name):
    """These are legitimately mailed, so refusing them outright would
    break normal use - the user is warned instead."""
    assert check_attachment(name).verdict is Verdict.WARN


@pytest.mark.parametrize("name", [
    "report.pdf", "photo.jpg", "scan.png", "notes.txt", "sheet.xlsx",
    "slides.pptx", "doc.docx", "data.csv", "card.vcf",
])
def test_ordinary_documents_and_images_are_allowed(name):
    check = check_attachment(name)
    assert check.verdict is Verdict.ALLOW
    assert check.blocked is False


def test_oversized_attachments_are_blocked_before_decoding():
    check = check_attachment("huge.pdf", "application/pdf", MAX_ATTACHMENT_BYTES + 1)
    assert check.verdict is Verdict.BLOCK
    assert "limit" in check.reason.lower()


def test_extensionless_and_unknown_types_warn():
    assert check_attachment("README").verdict is Verdict.WARN
    assert check_attachment("thing.qqq").verdict is Verdict.WARN


def test_check_never_raises_on_hostile_input():
    for hostile in (None, "", "." * 500, "\x00", "\u202e" * 40, "a" * 100_000):
        assert check_attachment(hostile) is not None


# ---------------------------------------- integration with MIME parsing

def test_parser_reports_guarded_attachment_metadata():
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    from app.email.message_parser import list_attachments

    msg = MIMEMultipart()
    msg.attach(MIMEText("body", "plain"))
    for filename, payload in (
        ("report.pdf", b"%PDF-1.4 fake"),
        ("../../evil.exe", b"MZ fake"),
    ):
        part = MIMEApplication(payload, _subtype="octet-stream")
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    atts = list_attachments(msg)
    assert len(atts) == 2
    by_name = {a["name"]: a for a in atts}
    assert by_name["report.pdf"]["verdict"] == "allow"
    # Path stripped AND the executable refused.
    assert "evil.exe" in by_name
    assert by_name["evil.exe"]["verdict"] == "block"
    assert all("/" not in a["name"] and "\\" not in a["name"] for a in atts)


def test_inline_cid_images_are_not_listed_as_attachments():
    """A cid: image is part of the rendered body, not a file the user
    should see offered as an attachment."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.image import MIMEImage
    from email.mime.text import MIMEText

    from app.email.message_parser import list_attachments

    msg = MIMEMultipart("related")
    msg.attach(MIMEText("<img src='cid:logo'>", "html"))
    img = MIMEImage(b"\x89PNG\r\n\x1a\n", "png")
    img.add_header("Content-ID", "<logo>")
    img.add_header("Content-Disposition", "inline", filename="logo.png")
    msg.attach(img)

    assert list_attachments(msg) == []


def test_malformed_mime_does_not_break_attachment_listing():
    import email as email_mod

    from app.email.message_parser import list_attachments

    broken = email_mod.message_from_bytes(
        b"Content-Type: multipart/mixed; boundary=X\r\n\r\n--X\r\n"
        b"Content-Disposition: attachment; filename=\r\n\r\ntruncated"
    )
    assert isinstance(list_attachments(broken), list)

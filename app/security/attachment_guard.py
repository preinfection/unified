"""Attachment hardening for untrusted email parts.

This is NOT antivirus. It does no signature matching, no heuristic
emulation, and no cloud lookup - deliberately, because bundling a real
scanning engine is not something this application can do safely or
honestly, and a fake one would be worse than none. Windows Defender
already scans files written to disk via the standard filesystem paths
this module uses; nothing here tries to replace it.

What it does do is refuse to let a hostile *filename* or an implausible
*size* turn into a filesystem or execution problem:

  - filenames are reduced to a bare, safe leaf name (no directories, no
    traversal, no NUL/control characters, no Windows reserved device
    names, no trailing dot/space tricks, no right-to-left override
    disguises)
  - obviously executable or script content is refused outright rather
    than being handed to the shell
  - archive members are resolved against their destination and refused
    if they would land outside it (zip-slip)
  - oversized parts are refused before being decoded into memory

Unified never auto-opens, auto-extracts, or auto-executes an attachment.
The guard's verdict is advisory to the UI for display, and mandatory on
the save path.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath

# A single decoded attachment is refused past this, before the payload is
# materialised - well above any real document, well below "exhaust RAM".
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024

_MAX_NAME_LEN = 120
_FALLBACK_NAME = "attachment"

# Directly executable, or executed by a shell/interpreter on double-click
# under Windows. This is the refuse-outright set.
_EXECUTABLE_EXTS = frozenset("""
exe com scr pif cpl msi msp mst dll ocx sys drv efi
bat cmd vbs vbe js jse wsf wsh wsc ws sct
ps1 psm1 psd1 ps1xml psc1 msh msh1 msh2 mshxml
hta lnk inf reg scf url application appref-ms gadget jnlp
jar apk msc cab chm hlp job
py pyw pyz pyc rb pl sh ksh csh bash
vb vbscript vsmacros vsw vxd xnk shb shs prg
""".split())

# Runs code only after an explicit user action inside another app (macro
# prompt, mount, installer). Surfaced as a warning rather than refused,
# because these are also legitimately mailed.
_RISKY_EXTS = frozenset("""
docm dotm xlsm xltm xlam xlsb pptm potm ppam sldm
iso img vhd vhdx dmg deb rpm
zip rar 7z tar gz bz2 xz tgz z lz lzma arj ace
""".split())

# Extensions that are safe to *store*; nothing here executes on open.
_KNOWN_SAFE_EXTS = frozenset("""
pdf txt csv log md rtf
png jpg jpeg gif bmp webp tiff tif svg ico heic
doc docx xls xlsx ppt pptx odt ods odp pages numbers
mp3 wav ogg flac m4a aac mp4 mov avi mkv webm
eml msg ics vcf json xml yaml yml
""".split())

# Windows refuses (or bizarrely reinterprets) these as file names,
# with or without an extension.
_WINDOWS_RESERVED = frozenset("""
con prn aux nul
com1 com2 com3 com4 com5 com6 com7 com8 com9
lpt1 lpt2 lpt3 lpt4 lpt5 lpt6 lpt7 lpt8 lpt9
""".split())

# Bidi controls let "invoice‮gnp.exe" render as "invoicexe.png" -
# a real, widely used disguise for executable attachments.
_BIDI_CONTROLS = "‪‫‬‭‮⁦⁧⁨⁩‎‏"
_UNSAFE_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')


class Verdict(str, Enum):
    ALLOW = "allow"      # safe to store and hand to the OS on request
    WARN = "warn"        # storable, but the user is told why it's risky
    BLOCK = "block"      # refused; never written, never opened


@dataclass(frozen=True)
class AttachmentCheck:
    """The guard's decision about one attachment."""
    safe_name: str
    verdict: Verdict
    reason: str

    @property
    def blocked(self) -> bool:
        return self.verdict is Verdict.BLOCK


def sanitize_filename(raw: str | None) -> str:
    """Reduce an attacker-controlled attachment name to a bare, safe leaf.

    Handles, in order: bidi/RTL-override disguises, both POSIX and
    Windows path separators (a name is never allowed to carry a
    directory), traversal segments, control characters and the Windows
    reserved punctuation set, Windows reserved device names, and the
    trailing dot/space that Windows silently strips (which is what lets
    "evil.exe." slip past a naive extension check).
    """
    name = (raw or "").strip()

    # Strip bidi controls before anything else so the visible name and
    # the real name cannot disagree.
    name = "".join(ch for ch in name if ch not in _BIDI_CONTROLS)
    # Normalise so lookalike/compatibility forms collapse to one spelling.
    name = unicodedata.normalize("NFKC", name)

    # Take the leaf under BOTH path flavours - an attachment named
    # "..\\..\\Startup\\x" must not keep any of that structure.
    name = PureWindowsPath(PurePosixPath(name).name).name

    # Anything still resembling traversal is not a usable name.
    if name in ("", ".", ".."):
        return _FALLBACK_NAME

    name = _UNSAFE_CHARS_RE.sub("_", name)
    # Windows drops trailing dots/spaces; strip them ourselves so the
    # stored name is the name the checks were performed against.
    name = name.rstrip(". ").strip()
    if not name:
        return _FALLBACK_NAME

    stem, dot, ext = name.partition(".")
    if stem.lower() in _WINDOWS_RESERVED:
        name = f"_{name}"

    if len(name) > _MAX_NAME_LEN:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 12:
            keep = _MAX_NAME_LEN - len(ext) - 1
            name = f"{stem[:keep]}.{ext}"
        else:
            name = name[:_MAX_NAME_LEN]

    return name or _FALLBACK_NAME


def _extension(name: str) -> str:
    return name.rpartition(".")[2].lower() if "." in name else ""


def _has_deceptive_double_extension(name: str) -> bool:
    """"invoice.pdf.exe" - a document-looking extension followed by an
    executable one. The executable extension is what actually runs."""
    parts = [p.lower() for p in name.split(".") if p]
    if len(parts) < 3:
        return False
    return parts[-1] in _EXECUTABLE_EXTS and parts[-2] in (
        _KNOWN_SAFE_EXTS | _RISKY_EXTS
    )


def check_attachment(filename: str | None, content_type: str = "",
                     size: int | None = None) -> AttachmentCheck:
    """Classify one attachment. Never raises - a part this can't make
    sense of is refused, not passed through."""
    safe = sanitize_filename(filename)
    ext = _extension(safe)

    if size is not None and size > MAX_ATTACHMENT_BYTES:
        mb = MAX_ATTACHMENT_BYTES // (1024 * 1024)
        return AttachmentCheck(safe, Verdict.BLOCK,
                               f"Larger than the {mb} MB attachment limit")

    if _has_deceptive_double_extension(safe):
        return AttachmentCheck(
            safe, Verdict.BLOCK,
            "Disguised executable (a document extension followed by a program one)",
        )

    if ext in _EXECUTABLE_EXTS:
        return AttachmentCheck(safe, Verdict.BLOCK,
                               f"Executable or script attachment (.{ext})")

    # A part claiming an executable MIME type is refused even if the name
    # was laundered to look harmless.
    ctype = (content_type or "").lower().strip()
    if ctype in ("application/x-msdownload", "application/x-executable",
                 "application/x-dosexec", "application/vnd.microsoft.portable-executable",
                 "application/x-msdos-program", "application/x-sh",
                 "application/x-bat", "application/hta"):
        return AttachmentCheck(safe, Verdict.BLOCK,
                               f"Executable content type ({ctype})")

    if ext in _RISKY_EXTS:
        return AttachmentCheck(
            safe, Verdict.WARN,
            f"Archives and macro-enabled files (.{ext}) can carry executable content",
        )

    if ext and ext not in _KNOWN_SAFE_EXTS:
        return AttachmentCheck(safe, Verdict.WARN,
                               f"Unrecognised attachment type (.{ext})")

    if not ext:
        return AttachmentCheck(safe, Verdict.WARN,
                               "Attachment has no file extension")

    return AttachmentCheck(safe, Verdict.ALLOW, "")


def safe_destination(directory: str | os.PathLike, filename: str | None) -> Path:
    """Resolve where an attachment may be written, guaranteeing the result
    is inside `directory`.

    Used for both save-to-disk and (should Unified ever extract one)
    archive members: resolving the candidate and re-checking containment
    is what defeats zip-slip, including via symlinked parents, because the
    check happens on the *resolved* path rather than on the string.
    """
    base = Path(directory).resolve()
    candidate = (base / sanitize_filename(filename)).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError(
            f"Refusing to write outside {base}: {filename!r} resolved to {candidate}"
        )
    return candidate


def is_archive_member_safe(member_name: str) -> bool:
    """Whether an archive entry can be extracted without escaping.

    Refuses absolute paths, drive letters, and any traversal segment -
    checked on the raw member name, because an archive entry is not
    obliged to be a bare leaf the way an attachment filename is.
    """
    if not member_name or member_name in (".", ".."):
        return False
    normalised = member_name.replace("\\", "/")
    if normalised.startswith("/") or PureWindowsPath(member_name).drive:
        return False
    return ".." not in PurePosixPath(normalised).parts

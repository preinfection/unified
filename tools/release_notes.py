"""Print a GitHub release body: one version's RELEASE_NOTES.md section,
then how to download and install it.

Usage: python tools/release_notes.py 1.4.0 [OUTPUT_FILE]

Writes UTF-8 to OUTPUT_FILE when given (safe on Windows, where a piped
stdout uses the console code page), else to stdout.

The section runs from its "## v<version>" heading to the next "## v"
heading. The heading itself is left out: the release title already says
which version this is, and the in-app Changelog drops a leading heading
that restates it anyway.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def section(version: str, text: str) -> str:
    lines = text.splitlines()
    heading = f"## v{version}"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        raise SystemExit(f"No '{heading}' section in RELEASE_NOTES.md") from None
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## v")), len(lines))
    body = "\n".join(lines[start + 1:end]).strip()
    if not body:
        raise SystemExit(f"The '{heading}' section is empty")
    return body + "\n"


def download(version: str) -> str:
    return f"""
---

## Download

**Unified-Setup-v{version}.exe** installs Unified, with optional Start menu
and desktop shortcuts, and replaces an earlier installed version in place.

**Unified-v{version}-windows.zip** is the same app without an installer:
unzip it anywhere and run `Unified\\Unified.exe`.

Either way, accounts, mail and settings live in `%APPDATA%\\Unified`, not
next to the app, so a new version picks them up (including from the v1.3.0
zip) and uninstalling never removes them.

Neither file is code-signed, so Windows SmartScreen warns the first time:
**More info -> Run anyway**. `SHA256SUMS.txt` lists both files' checksums.

Gmail accounts need a Google OAuth client file (`credentials.json`, type
"Desktop app", with the Gmail API enabled), chosen once in Settings. IMAP
accounts need nothing extra.

Requires 64-bit Windows 10 or 11.
"""


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    body = section(sys.argv[1], notes) + download(sys.argv[1])
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_text(body, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(body)

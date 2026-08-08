# Unified

Unified is a Windows desktop email client that merges multiple Gmail and
IMAP accounts into a single inbox. Instead of juggling separate browser
tabs or apps per account, every message downloads into one local,
searchable, encrypted cache that opens instantly and works offline.

The app is built with Python, PySide6, and SQLite, with a dark, native
desktop UI. It targets people with several active mailboxes who want one
place to read, search, and triage everything without re-authenticating
or re-syncing every time they switch accounts.

Sync is verified rather than assumed: every import is checked against
the server's own message count, failures are reported honestly instead
of silently dropped, and the local database self-checks and repairs on
every launch.

![Unified main window](assets/screenshot.png)

## Files

| File | What it is |
| ---- | ---------- |
| `run.py` | Launches the app from source |
| `build.py` | Builds the packaged `.exe` with PyInstaller |
| `requirements.txt` | Python dependencies |
| `installer/Unified.iss` | Inno Setup script that builds the Windows installer |
| `app/main.py` | Application entry point |
| `app/config.py` | User settings and `%APPDATA%` paths |
| `RELEASE_NOTES.md` | Version history and what changed per release |
| `tests/` | Automated test suite (pytest) |

## Requirements

- Windows 10/11
- Python 3.10+ (only for running from source - the packaged `.exe` needs nothing)

## Installation

**For most users:** download `Unified-Setup-v1.1.0.exe` from the
[Releases](../../releases) page and run it. No Python or manual copying
required. The wizard lets you pick the install location, both desktop
and Start Menu shortcuts are optional, and a normal Windows uninstall
entry is created. Installing, upgrading, or uninstalling never touches
`%APPDATA%\Unified` - your accounts, settings, and mailbox cache are
only ever changed by the app itself.

**From source:**

```powershell
git clone <this repo>
cd Unified
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py
```

Run `run.py` or `python -m app.main` from the project root - not
`python app\main.py` directly, which would shadow the standard library
`email` module.

**Building the installer:**

```powershell
.venv\Scripts\python build.py
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\Unified.iss
```

The first command produces `dist\Unified\Unified.exe` via PyInstaller.
The second requires [Inno Setup 6](https://jrsoftware.org/isinfo.php)
and packages that build into `release\Unified-Setup-vX.Y.Z.exe`. The
installer's `AppId` is fixed so future versions upgrade in place instead
of installing side by side - don't regenerate it.

**Running tests:**

```powershell
.venv\Scripts\python -m pytest tests -v
```

If you're upgrading from the older "UnifiedMailbox" build, the new app
copies your database, settings, and stored sign-ins over automatically
on first launch. Nothing needs to be done by hand, and the old folder is
left in place as a backup.

## Usage

On first launch the app opens to an empty inbox - there's nothing to
configure before adding an account. The sidebar lists Unified Inbox,
Starred, Sent, and Trash across every connected account, plus a status
line per account showing live sync progress.

Common actions:

- **Add account** - sidebar → Add account, then Gmail or custom IMAP/SMTP
- **Search** - the search box scopes to whatever's currently shown (one
  account or everything) and always reaches the full local cache, not
  just what's on screen
- **Star / mark read / delete** - from the message list context menu or
  the reading pane toolbar; changes sync back to the server in the
  background
- **Compose** - plain-text mail from any connected account
- **Console** - a collapsible log pane with category filters (Sync,
  Errors, Database, API) for diagnosing sync issues

## Configuration

App-wide options live in **Settings**: sync interval, how many messages
are shown per view, and whether desktop notifications are enabled for
new mail.

**Gmail (OAuth2, recommended).** Google requires every installation of
an open-source app to use its own OAuth client:

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. **APIs & Services → Library** → enable the **Gmail API**
3. **APIs & Services → OAuth consent screen** → configure (External, add
   yourself as a test user)
4. **APIs & Services → Credentials → Create credentials → OAuth client
   ID** → type **Desktop app** → download `credentials.json`
5. In Unified: **Settings → Select credentials.json…**
6. **Add account → Gmail** to sign in

Your Google password is never seen by the app - only the OAuth token is
stored, and only in the Windows Credential Manager. Repeat step 6 for
additional Gmail accounts.

**Custom IMAP/SMTP.** Add account → Custom IMAP/SMTP, then enter the
server details (IMAP over SSL, typically port 993; SMTP with STARTTLS on
587 or SSL on 465). The password is verified against the server and
stored only in the Windows Credential Manager - use an app password if
the provider requires 2FA.

## How it works

The initial import paginates through the full mailbox with batched,
rate-limit-aware requests. Sync is metadata-first: headers, flags, and
snippets land quickly, the newest messages get bodies pre-downloaded,
and the rest download on demand when opened. Completion is checked
against the server's own message count, so the app never reports
"ready" without verifying - a partial sync says so explicitly and
retries on the next refresh.

Each account moves through an explicit state machine (Connecting,
Downloading list, Syncing metadata, Downloading bodies, Verifying,
Complete, or Failed), shown live in the sidebar. Accounts sync on
independent background workers, two at a time, with the rest queued and
visibly waiting - the app stays fully usable throughout, and accounts
can be added mid-sync.

The reading pane is race-safe: clicking rapidly between messages never
shows stale content, since a body arriving late for a previously
selected email is discarded and duplicate fetches are suppressed. On
every launch, the local database runs a structural integrity check
(duplicate ids, orphaned rows, invalid folders) and repairs what it can
without ever crashing on a damaged file.

## Performance / Technical details

The message list is virtualized - a `QAbstractListModel` backed by a
custom-painted row delegate, not one widget per row - so it stays smooth
past 20,000 cached messages. Nothing renders beyond what's actually on
screen.

The list view has a display limit for performance, never for data: the
status bar and a "Load more" button always show the true count (e.g.
"Showing newest 1,000 of 20,100 emails"), and search reaches the entire
local cache regardless of that limit. Everything is cached in SQLite, so
the app opens instantly and stays usable offline for reading.

## Security notes

- Gmail OAuth tokens and IMAP passwords are stored via
  [keyring](https://pypi.org/project/keyring/) in the Windows Credential
  Manager - never written to disk in plaintext.
- Gmail access uses the official Gmail API with the `gmail.modify` and
  `gmail.send` scopes. IMAP uses SSL; SMTP uses SSL or STARTTLS.
- The local SQLite cache is encrypted at rest (AES-256-GCM). The key is
  wrapped with Windows DPAPI - the same mechanism Chrome/Edge use for
  saved passwords - so it only unwraps under your specific Windows user
  account on this machine. See [RELEASE_NOTES.md](RELEASE_NOTES.md) for
  the full threat model.
- Logging never writes OAuth tokens, passwords, client secrets, message
  content, or attachment names. Accounts are logged by a local numeric
  ID, not by email address.
- Nothing under `%APPDATA%\Unified` is ever written inside the project
  folder, and none of it is tracked by git - see `.gitignore`.

## Known limitations

- Windows only - relies on the Windows Credential Manager and DPAPI.
- Bring your own Google OAuth client; there's no bundled default.
- Attachments are indicated, not downloadable, yet.
- Compose is plain text only - no formatting, no outgoing attachments.
- Per-account view is inbox-only; Starred/Sent/Trash are unified
  (all-accounts) views.
- Encryption at rest protects a stolen disk or leaked backup, not
  malware already running as you while the app is open - see
  [Security notes](#security-notes).

## Project structure

```
Unified/
├── app/
│   ├── ui/            # PySide6 widgets: main window, dialogs, stylesheet
│   ├── database/      # SQLite storage (accounts + cached emails)
│   ├── email/         # Gmail API, IMAP, SMTP clients and MIME parsing
│   ├── auth/          # OAuth2 flow and OS-keyring secret storage
│   ├── security/      # at-rest database encryption (DPAPI + AES-256-GCM)
│   ├── services/      # account manager, background sync, notifications
│   ├── config.py      # paths and user settings (%APPDATA%)
│   ├── migration.py   # one-time carry-over from older installs
│   ├── logging_setup.py
│   └── main.py        # application entry point
├── assets/            # icon + screenshots for the repo/README
├── installer/         # Inno Setup script (Unified-Setup-vX.Y.Z.exe)
├── tests/             # pytest suite
├── build.py           # PyInstaller build script
├── run.py             # launcher
├── requirements.txt
└── README.md
```

## License

MIT

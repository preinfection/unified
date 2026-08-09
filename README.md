# Unified

Unified is a Windows desktop email client that combines multiple Gmail and IMAP accounts into one inbox. It provides a fast searchable local cache so you can read, search, and organize mail without switching between accounts.

Built with Python, PySide6, and SQLite, Unified focuses on a modern desktop experience with offline access, background syncing, and secure local storage.

## Features

* Multiple Gmail and IMAP accounts in one inbox
* Fast local email search
* Offline access to cached messages
* Modern native Windows desktop interface
* Encrypted local email cache
* Background syncing with progress tracking
* Secure credential storage

## Preview

![Unified main window](assets/screenshot.png)

## Requirements

* Windows 10/11
* Python 3.10+ (only required for running from source)

## Installation

### For most users

1. Download the latest release:

```
Unified-Setup-v1.2.1.exe
```

2. Run the installer.

No Python setup or manual configuration is required.

### From source

```powershell
git clone https://github.com/preinfection/unified.git
cd unified
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py
```

This launches Unified directly from the source code.

## Files

| File                    | Description                     |
| ----------------------- | ------------------------------- |
| `run.py`                | Launches the application        |
| `build.py`              | Builds the packaged executable  |
| `requirements.txt`      | Python dependencies             |
| `installer/Unified.iss` | Windows installer configuration |
| `app/main.py`           | Application entry point         |
| `app/config.py`         | Settings and application paths  |
| `RELEASE_NOTES.md`      | Version history                 |
| `tests/`                | Automated test suite            |
| `assets/`               | Images and application assets   |

## Usage

1. Open Unified.
2. Add a Gmail or Custom IMAP/SMTP account.
3. Wait for synchronization to complete.
4. Read, search, organize, and manage messages from one inbox.

Available actions:

* Search across your entire local mailbox cache
* Star, mark read, and manage messages
* Compose plain-text emails
* Monitor sync progress and errors from the console

## How it works

Unified keeps a local SQLite database containing your synchronized mailbox data.

Accounts sync in the background:

* Message information is downloaded first for fast loading.
* Email bodies are downloaded when needed.
* Sync progress is shown while accounts are updating.
* Completed syncs are verified against the server.

The application remains usable while synchronization is running.

## Security

* Gmail authentication uses OAuth2; no Google password ever reaches the app.
* IMAP/SMTP credentials and the Gmail OAuth token are stored only in the
  Windows Credential Manager - never written to disk in plaintext.
* All network connections are encrypted in transit: IMAP is SSL-only,
  SMTP uses implicit SSL or STARTTLS before login, and the Gmail API is
  HTTPS-only (enforced by Google's own client library).
* The local mailbox cache is encrypted at rest with AES-256-GCM; the key
  is generated once and wrapped with Windows DPAPI, so it only unwraps
  under this Windows user account on this machine. See
  [RELEASE_NOTES.md](RELEASE_NOTES.md) for the full threat model -
  stated plainly, including what this does *not* protect against.
* Logs do not contain passwords, tokens, or private message content.

**What this is not:** Unified is not end-to-end encrypted mail. Gmail
and IMAP are standard protocols - your mail provider can read message
content, exactly as with any other Gmail/IMAP client, and nothing here
changes that. "Encrypted locally" (in the app's sidebar, and above)
refers specifically to the local cache and stored credentials on your
machine, not the message content itself in transit or at your
provider. Real end-to-end encryption (PGP/S-MIME) would require key
management and a compatible setup on the recipient's end for every
correspondent - it is not implemented, and this is not a claim made
anywhere in the app.

## Technical details

* Language: Python 3.10+
* UI framework: PySide6
* Database: SQLite
* Authentication: Gmail API, IMAP, SMTP
* Packaging: PyInstaller + Inno Setup
* Storage: Encrypted local cache
* Performance: Virtualized message lists designed for large mailboxes

## Known limitations

* Windows only
* Google OAuth requires your own `credentials.json`
* Attachments are detected but not downloadable yet
* Email composition currently supports plain text only
* Per-account views are currently inbox-focused

## Project structure

```text
Unified/
├── app/
│   ├── ui/            # Desktop interface
│   ├── database/      # SQLite storage
│   ├── email/         # Gmail, IMAP, SMTP handling
│   ├── auth/          # Authentication and credentials
│   ├── security/      # Encryption systems
│   ├── services/      # Background services
│   └── main.py       # Application entry point
├── assets/            # Images and assets
├── installer/         # Windows installer files
├── tests/             # Automated tests
├── build.py           # Build script
├── run.py             # Source launcher
├── requirements.txt
└── README.md
```

## License

MIT

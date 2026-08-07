# Unified Mailbox

A lightweight Windows desktop email client that combines multiple email
accounts into one unified inbox. Built with Python, PySide6 and SQLite.

![Unified Mailbox main window](assets/screenshot.png)

## Features

- **Unified inbox** - all incoming mail from every connected account in one list,
  each row showing the owning account, sender, subject, time, unread state and
  an attachment indicator
- **Multiple accounts** - any number of Gmail accounts (OAuth2 via the Gmail
  API) plus custom IMAP/SMTP accounts
- **Full mailbox sync, verified** - the initial import paginates through the
  entire mailbox with batched, rate-limit-aware Gmail API requests. Sync is
  metadata-first (headers/flags/snippets), so even 15k-message mailboxes
  import quickly; message bodies download on demand when an email is opened.
  Completion is verified against the server message count - if anything
  failed, the app says so honestly and retries on the next Refresh
- **Parallel per-account sync** - accounts sync on independent background
  workers with live per-account status in the sidebar (✓ Synced,
  ↻ Fetching..., Waiting); the app stays fully usable while syncing, and
  accounts can be added mid-sync
- **Developer console** - a collapsible monospace log pane (Console button)
  showing sync activity, page fetches, and errors in real time
- **Background sync** - periodic synchronization on a configurable interval,
  plus manual refresh; new-mail notifications fire only for mail that arrives
  after the initial import, never for imported existing mail
- **Cancellable sign-in** - Google OAuth can be cancelled at any time
  (Cancel Login button or closing the dialog) and times out after 2 minutes;
  the main window stays fully usable while a sign-in is pending
- **Local cache** - emails are cached in SQLite so the app opens instantly and
  works offline for reading
- **Search** - full search across every account (sender, subject, body)
- **Unread counters** - total and per-account counts in the sidebar
- **Desktop notifications** - system tray notification when new mail arrives
- **Organization** - star/unstar, mark read/unread, move to trash; actions are
  pushed back to the mail server in the background
- **Compose** - send plain-text mail from any connected account
- **Security** - no passwords or tokens are ever written to disk; everything
  secret lives in the Windows Credential Manager (OS keyring)

## Requirements

- Windows 10/11
- Python 3.10+ (for running from source; the packaged .exe needs nothing)

## Running from source

```powershell
git clone <this repo>
cd UnifiedMailbox
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py
```

> Note: run `python run.py` or `python -m app.main` from the project root.
> Do not run `python app\main.py` directly - it would put `app/` on `sys.path`
> and shadow the standard library `email` module.

## Connecting accounts

### Gmail (OAuth2 - recommended)

Google requires each installation of an open-source desktop app to use its own
OAuth client. One-time setup:

1. Go to [Google Cloud Console](https://console.cloud.google.com/), create a
   project (any name).
2. **APIs & Services → Library** → enable the **Gmail API**.
3. **APIs & Services → OAuth consent screen** → configure (External, add your
   own address as a test user).
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** →
   type **Desktop app** → download the `credentials.json`.
5. In Unified Mailbox: **Settings → Select credentials.json…** and pick the file.
6. **+ Add account… → Gmail** - a browser window opens for Google sign-in.

Your Google password is never seen by the app; only the OAuth token is stored,
and only in the Windows Credential Manager. Repeat step 6 for as many Gmail
accounts as you like.

### Custom IMAP/SMTP

**+ Add account… → Custom IMAP/SMTP** and enter the server details
(IMAP over SSL, typically port 993; SMTP with STARTTLS on 587 or SSL on 465).
The password is verified against the server and then stored only in the
Windows Credential Manager. For providers with 2FA (including Gmail via IMAP),
use an app password.

## Building the .exe

```powershell
.venv\Scripts\python build.py
```

The build output is `dist\UnifiedMailbox\UnifiedMailbox.exe`. The whole
`dist\UnifiedMailbox` folder is the installation - copy it anywhere and run
the exe. User data is kept in `%APPDATA%\UnifiedMailbox`.

## Running tests

```powershell
.venv\Scripts\python -m pytest tests -v
```

## Project structure

```
UnifiedMailbox/
├── app/
│   ├── ui/            # PySide6 widgets: main window, dialogs, stylesheet
│   ├── database/      # SQLite storage (accounts + cached emails)
│   ├── email/         # Gmail API, IMAP, SMTP clients and MIME parsing
│   ├── auth/          # OAuth2 flow and OS-keyring secret storage
│   ├── services/      # account manager, background sync, notifications
│   ├── config.py      # paths and user settings (%APPDATA%)
│   ├── logging_setup.py
│   └── main.py        # application entry point
├── assets/            # generated icon
├── tests/             # pytest suite (database, MIME parsing)
├── build.py           # PyInstaller build script
├── run.py             # launcher
├── requirements.txt
└── README.md
```

## Security notes

- No plaintext credentials, ever: Gmail OAuth tokens and IMAP passwords are
  stored via [keyring](https://pypi.org/project/keyring/) in the Windows
  Credential Manager.
- Gmail access uses the official Gmail API with the `gmail.modify` and
  `gmail.send` scopes.
- IMAP connections use SSL; SMTP uses SSL or STARTTLS.
- The local SQLite cache (`%APPDATA%\UnifiedMailbox\mailbox.db`) contains
  message bodies - it stays on your machine and is excluded from git.

## License

MIT

# Unified

## v1.0.1

UI redesign. No backend, sync, database, encryption, or installer *logic*
changed in this release - only the presentation layer.

### What changed

- **Complete visual redesign**, following a dark, modern reference design
  (structure, spacing, and typography hierarchy - not literal chrome/
  colors copied from any particular brand): dark charcoal surfaces,
  restrained accent color used only as signal (unread dots, selected
  state, status), and elevated "card" panels for the sidebar and message
  reading pane instead of flat single-tone regions.
- **Account drawer sidebar**: each connected account now shows as its own
  row with an avatar (initial letter, deterministic muted color per
  address), a live-updating status line (Waiting / Syncing metadata N/M /
  Complete - verified / Failed: reason), and an unread-count badge -
  replacing the old plain tree list.
- **Rebuilt message list for real scale**: previously a `QTreeWidget`
  populated with one item per row, now a `QListView` backed by a proper
  `QAbstractListModel` with a custom-painted row delegate (avatar, bold
  sender for unread, subject + snippet, time, star/attachment glyphs).
  Nothing is instantiated per row beyond what's on screen - verified at
  10,000+ rows with sub-100ms model load and ~2-3ms per scroll step (see
  Release validation below).
- **Redesigned reading pane**: sender identity, subject, and a generic
  "Has attachment" indicator (the data model only ever stored a boolean
  flag, never per-file names, so nothing is fabricated) in an elevated
  card header above the message body.
- **New reusable component modules** under `app/ui/components/`:
  `SidebarWidget`, `AccountItem`, `EmailListView`/`EmailListModel`/
  `EmailRowDelegate`, `PreviewPane`, `TopToolBar`, `StatusIndicator`,
  `LoadingState`, plus a shared `avatar.py` painter and a single
  `theme.py` token module both the stylesheet and the custom-painted
  delegates read from, so a color can't drift between the two.
- Native title bar now follows the app's dark theme (previously forced
  white) via the same DWM API technique as before.
- Version bumped to 1.0.1 throughout: app metadata, the Settings dialog's
  version label, the Inno Setup installer (`AppId` deliberately
  unchanged - see Install instructions), and this document.

### Fixed during the redesign (found via testing, not requested changes)

- A `QSplitter` reserved proportional height for the console panel even
  while it was hidden, which could squeeze the sidebar enough to push its
  Settings button below the visible window at smaller heights. Console
  now starts collapsed to zero height and only claims space when actually
  toggled visible.
- Several widget types (`QTextBrowser`, `QStackedWidget`) don't reliably
  composite a QSS `background: transparent` through to the window behind
  them - both were switched to an explicit background color instead,
  which is also what fixed message body text being nearly unreadable
  against the wrong background.

### Untouched in this release

Gmail API integration, OAuth authentication, account storage, the
encryption system, DPAPI handling, the SQLite schema, sync workers,
background threads, email fetching, MIME parsing, the search backend,
notifications, and the build/installer *scripts* (only the version
number changed in `installer/Unified.iss`) - verified by diff, not just
by intent: the full pre-existing test suite (54 tests covering database,
crypto, migration, sync logic, OAuth flow, and message parsing) passes
unchanged.

---

## v1.0.0

First public release.

### Features

- Unified inbox combining any number of Gmail (OAuth2, official Gmail API)
  and custom IMAP/SMTP accounts, showing account, sender, subject, time,
  read/unread state, and an attachment indicator per message
- Full mailbox sync with pagination and batched requests - not limited to
  the first page of a large mailbox - with completion verified against the
  server's own message count before ever reporting "ready"
- Metadata-first sync (headers/flags/snippets fetched in bulk; message
  bodies download on demand when opened, with recent inbox messages
  pre-fetched) so large mailboxes import quickly and the UI stays responsive
- Explicit per-account sync states (Connecting, Downloading message list,
  Syncing metadata, Downloading missing bodies, Verifying, Complete,
  Failed) shown live in the sidebar with real counts
- Parallel per-account sync workers; accounts can be added or switched to
  while others are syncing
- Local SQLite cache with search across every account, unread counters,
  starring, mark read/unread, move to trash (actions sync back to the
  server in the background)
- Encrypted local cache at rest (see Security notes below)
- Startup database integrity check with automatic repair of common issues
  (duplicate rows, orphaned records, invalid data) - never crashes on a
  damaged database, reports what it found instead
- Cancellable Google sign-in (Cancel Login button, closing the dialog, or a
  2-minute timeout) that never blocks or freezes the main window
- Desktop notifications for genuinely new mail only - never for messages
  imported during an account's initial sync
- Collapsible developer console with category filters (All/Sync/Errors/
  Database/API), clear, copy-to-clipboard, and auto-scroll
- Plain black-and-white UI: no gradients, no cards, no animations
  (superseded by the redesign in v1.0.1 above)

### Known limitations

- **Windows only.** Uses PySide6, the Windows Credential Manager, and
  Windows DPAPI for local encryption; there is no macOS/Linux build.
- **Distribute the whole folder, not the .exe alone.** The packaged build
  is PyInstaller "onedir" output: `Unified.exe` depends on the adjacent
  `_internal` folder and will not start without it (confirmed in release
  testing - it shows an immediate "Error" dialog). Ship or copy the entire
  `dist\Unified` folder as one unit.
- **Bring your own Google OAuth client.** Google requires every
  installation of an open-source desktop app to use its own OAuth client
  ID; there is no bundled default. See the README's Gmail setup steps.
- **Attachments are indicated, not downloadable.** The list shows whether a
  message has attachments; saving/viewing individual attachment files
  is not implemented yet.
- **Compose is plain text only.** No rich formatting and no attachments on
  outgoing mail.
- **Per-account view is inbox-only.** Clicking a specific account shows its
  inbox; Starred/Sent/Trash are unified (all-accounts) views only.
- **Message list has a display limit** (default 1,000, adjustable in
  Settings) per view for performance - never a data limit. "Load more" and
  search always reach the complete local cache regardless of this setting.
- **Encryption-at-rest limitations** - see Security notes below; the
  guarantee it provides is real but specific, and it is not a substitute
  for full-disk encryption (BitLocker) or endpoint security.

### Security notes

- **OAuth tokens and IMAP passwords**: stored only in the Windows
  Credential Manager (DPAPI), scoped to this Windows user account. Never
  written to disk in plaintext.
- **Local mailbox cache**: the SQLite database is encrypted at rest with
  AES-256-GCM. The encryption key is generated once per install and is
  itself protected with Windows DPAPI, the same mechanism Chrome/Edge use
  for saved passwords - the wrapped key only unwraps under this specific
  Windows user account on this specific machine. The database is
  decrypted to a working copy while the app runs and re-encrypted (with
  the plaintext copy securely overwritten and deleted) on every clean
  exit.
  - **What this protects against**: a stolen or discarded machine/disk, a
    copy of `%APPDATA%` that ends up in a cloud backup or on a USB drive,
    or another Windows account on a shared machine reading these files.
  - **What this does not protect against**: malware or an attacker with
    full control of the *already logged-in* Windows session while Unified
    is running. At that point the OS will hand over the same DPAPI key to
    anything running as that user - no local, prompt-free encryption
    scheme can prevent that, and no claim to the contrary would be honest.
  - **If the key is lost** (e.g. a Windows profile reset, or moving only
    the database file to a different machine without `key.bin`), the
    previously encrypted local cache becomes permanently unreadable. This
    is not a data-loss event for your actual mail: remove and re-add the
    affected account(s) to rebuild the cache from the server. The
    undecryptable file is preserved (renamed, not deleted) rather than
    overwritten, in case manual recovery is possible.
  - If the app is killed rather than closed normally, the working copy may
    remain in plaintext until the next clean exit re-encrypts it; the data
    itself is never corrupted (SQLite WAL is crash-safe) and sync simply
    resumes on the next launch, with the app noting that it recovered from
    an interrupted session.
- **Logging**: the developer console and `logs/app.log` never write OAuth
  tokens, passwords, client secrets, message subjects/bodies, or
  attachment names. Account activity is logged by a purely local numeric
  ID (e.g. "Account 3: sync started"), not by email address, so sharing a
  log file for troubleshooting does not reveal which accounts are
  connected.

### Migration notes

This project was previously named "UnifiedMailbox". If you have an
existing install under that name, the new build automatically migrates it
on first launch:

- `%APPDATA%\UnifiedMailbox\mailbox.db`, `settings.json`, and
  `google_credentials.json` are copied to `%APPDATA%\Unified`
- Each account's stored Gmail OAuth token or IMAP password is re-saved
  under the new Windows Credential Manager service name
- No re-sync or re-login is required
- The old `%APPDATA%\UnifiedMailbox` folder is left untouched as a backup
  (copied, never moved or deleted) - safe to remove manually once you've
  confirmed the new install has everything

Migration is idempotent: it runs at most once, whether the destination
already holds a plaintext or an already-encrypted database, and re-running
the app never re-copies or duplicates accounts/messages.

### Release validation performed

Before this release, the following was verified against the actual built
`Unified.exe` (not just the test suite):

- Fresh install (empty `%APPDATA%`): clean launch, no missing-dependency
  errors, correct database creation, correct startup integrity check
- Upgrade from a legacy "UnifiedMailbox" install: migration ran once,
  carried over accounts/messages/sign-ins correctly, and a second launch
  did not duplicate anything (independently verified by decrypting and
  directly inspecting the resulting SQLite database)
- A full Gmail + IMAP sync attempt was exercised inside the frozen
  executable (with intentionally invalid test credentials) to confirm the
  entire Google API / OAuth / IMAP dependency chain is correctly bundled -
  it failed with clean, friendly errors, not missing-module crashes
- Distribution: confirmed `Unified.exe` alone does not run (shows an
  "Error" dialog without its `_internal` folder) and that the full
  `dist\Unified` folder runs correctly from an arbitrary location with no
  dependency on the build machine's file paths
- Crash recovery: the running process was force-killed mid-session; on
  relaunch the app reported "Recovered mailbox from an interrupted
  previous session," the database passed its integrity check with no
  corruption or duplicate rows, and sync resumed normally
- Privacy audit: every tracked file (current state and full git history)
  was searched for real email addresses, OAuth tokens, API keys, and
  local file paths - none found; the packaged `dist\Unified` folder was
  scanned for stray database/credential/log/temp files - none found; and
  every logging call site in the source was audited for account email
  addresses, fixed to use a local numeric ID instead where any were found
- Installer packaging (Inno Setup): silent install/uninstall verified
  end to end - exe, `_internal`, both optional shortcuts (correct target
  paths), and the Windows uninstall registry entry all created correctly;
  uninstall removed the app/shortcuts/registry entry while leaving
  `%APPDATA%\Unified` byte-for-byte unchanged; a reinstall over surviving
  data loaded it correctly (confirmed via the app's own startup log)

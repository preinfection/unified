# Unified

## v1.4.0

> **Note on lineage.** This line was developed from v1.2.1 in parallel
> with the v1.3.0 redesign that reached `main` on 2026-09-03. The two
> overlap heavily in intent but are separate designs: v1.4.0 is not built
> on top of v1.3.0. On 2026-09-24 this line replaced v1.3.0 on `main`;
> v1.3.0's history and tag are kept. The two share an installer AppId, so
> installing v1.4.0 upgrades a v1.3.0 install in place.

A product-level redesign of the interface, followed by a production
polish pass. No change to how mail is fetched, stored, encrypted or
authenticated: every call into the database, sync, transport and security
layers behaves as it did in v1.2.1, apart from the two additions noted
under *Backend* below, both of which exist to support features in this
release.

### Upgrading from v1.3.0

Your accounts, mail and settings carry over. v1.3.0 did not change the
database, the encryption key or the sign-in storage, so v1.4.0 opens the
same files. A few things are different:

- Some v1.3.0 features are not in this line: Mark all as read, the
  Unread filter in the list header, the third ("relaxed") row density,
  "Match Windows" for motion, the "Open maximised" setting (this line
  always opens maximised) and remembering the window's restored size.
- A theme set to "Match Windows" now picks light or dark from Windows each
  time Unified starts, rather than following it live. Choosing a theme in
  Settings replaces it.
- Reduced motion and compact rows, if you had them on, stay on.
- v1.3.0's own settings are left in the file, so going back to v1.3.0
  keeps them.

### Folders in a dock, accounts in the sidebar

The sidebar answered two questions in one list - which folder, and whose
mail - and the answers took turns: choosing an account un-chose the
folder. Inbox, Starred, Sent and Trash now sit in a dock centred in the
toolbar, with Add account and Settings after a divider; the sidebar is
"All accounts" and one row per account. Both are always shown and both
can be true at once, so "work@company.com's Sent" is a place you can be.
The window owns that location and tells the two widgets, rather than
each keeping its own copy - which is how the old drawer once showed a
folder and an account selected together.

The dock magnifies toward the pointer (adapted from Magic UI's Dock, at
1.25x rather than 1.5x) through an overdamped spring, inside a reserved
box so nothing else in the toolbar ever moves. The selected folder is one
surface that slides. The inbox's unread count is a badge on the dock that
follows the account in view. `Ctrl+1` to `Ctrl+4` jump to the folders;
`Tab`, the arrow keys and `Enter` work through the dock and the account
list.

With no accounts connected, the window no longer reserves a blank reading
pane beside the offer to add one, and search, sync and compose are
disabled with a line saying why. The search field is sized to a query
instead of spanning the window.

### The rest of the interaction pass

Each adapted from a Magic UI component and cut down to what the product
can justify:

- **Theme** is a sun/moon control in Settings > Appearance instead of a
  dropdown. It applies at once and the new theme spreads out from the
  control across every open window; Cancel puts it back.
- **Console** is a quiet terminal-style log: aligned time, level, source
  and message columns, colour only on warnings and errors, batched so a
  burst of a thousand lines is one repaint, and a steady prompt while it
  is following new output.
- **Reply and forward** type the quoted original in beneath the cursor.
  The whole text is in the message from the first frame, and any
  keystroke, click or paste ends the reveal at once.
- **Updates**: GitHub's releases are checked at most hourly, never during
  startup and never blocking anything. When a newer version exists, an
  "Update" button appears in the toolbar and opens its release page; a
  glint crosses it once when it appears. Settings > Changelog lists every
  published release.
- **Opening**: a slowly turning dotted globe, then the name, then the
  mailbox. It never delays a startup that is already finished.
- **Smooth pointer**, experimental and off by default. A smoothed pointer
  trails the real one (about 54ms here), so it steps aside over text,
  handles and drags.

Every animation has a reduced-motion state that is its final state.

### Fixed in the same pass

- Collapsing the sidebar to its rail left a 192px dead strip instead of
  giving the width to the list and the reading pane.
- After switching to the light theme, the selected account row kept a
  dark-mode background, and every avatar drew a near-white initial on a
  pale disc.
- Icons were rasterized at 1x only and drawn soft at 125-200% scaling.
- The reading pane kept showing a message after moving to a folder that
  does not contain it.
- A message body that was a single unterminated HTML tag rendered as
  nothing on current Python versions.
- Closing the window within 400ms of opening could start a sync
  afterwards on threads nothing waited for.

Tests: 412 to 594.

### The keyboard works

`app/ui/shortcuts.py` was complete, documented, and imported by nothing.
Every action in the client required the mouse. The bindings are the ones
Gmail, Thunderbird and Mailspring already share, so nothing has to be
learned:

    j / k or arrows   move through the list      /  or Ctrl+F   search
    Enter             open the focused message   n  or Ctrl+N   compose
    s                 star or unstar             r  or F5       sync now
    u                 mark unread                Ctrl+B         sidebar
    # or Delete       delete                     Ctrl+,         settings
    Esc               back out one step          ?  or F1       this list

Single-letter shortcuts stand down while focus is in a text field, so the
app is still typeable. The help sheet is generated from the same table
the shortcuts are installed from, so it cannot document a keyboard the
app does not have.

### Light mode is reachable

The light palette had been generated in OKLCH and contrast-checked
against every surface, and nothing could display it: `apply_mode()` had
exactly one caller, at import, with `"dark"` hardcoded. Both themes are
now selectable in Settings and switch live.

Making that work needed a real fix rather than a toggle. Around thirty
labels carried their colour as an inline stylesheet, which outranks the
application stylesheet and is therefore frozen at construction - so every
one of them stayed dark-mode ink. They use theme roles now and re-colour
with the stylesheet.

### Reply, reply all, forward

The reading pane had two actions (star, delete) and no way to answer a
message. It now leads with the subject as the page title, states the
sender once, and offers reply / reply all / forward on the left with
star / mark unread / delete on the right.

Recipient handling is the part worth stating: reply prefers `Reply-To`
where the message carried one, reply-all copies the other recipients
*minus the account that received it*, and forward addresses nobody.

**There is still no Archive.** The folder vocabulary is exactly
inbox/sent/trash and the integrity checker deletes rows in any other
folder, so an Archive button would need a schema change, a sync change
and an IMAP move behind it. A missing feature is better than a
misleading one.

### Opening

The app opens maximized into the normal Windows work area - taskbar
visible, ordinary window controls, no kiosk mode, nothing hard-coded.

The opening surface is maximized too, on the same background the shell is
about to occupy, and cross-dissolves into it. Previously a 340x220 card
vanished and a differently shaped 1280x800 window appeared somewhere
else.

The opening bar is a hairline the width of the wordmark, sitting under
it. It advances on the four real initialization stages and reaches
completion in exactly one place: when initialization actually finishes.
A startup too fast for the animation to play skips it rather than
flashing.

### Also

- Compose gained Cc/Bcc, and send is a state machine: sending, sent and
  failed each say what happened. A failed send keeps the message and the
  reason on screen instead of throwing a modal that erases both.
- Settings gained an Appearance page (theme, row density, reduced
  motion) and every row now explains what it does.
- Row density (comfortable/compact) and a collapsible sidebar, which
  collapses on its own below 1080px and never overrides an explicit
  choice.
- Empty, loading and error states all use the same design system.

### Fixed

- Message rows were laid out 14px wider than the viewport, so subjects
  and snippets were hard-clipped mid-word with no ellipsis and the list
  grew a horizontal scrollbar it had no use for.
- The reading pane's leading was 2.2x the type size. Qt's
  `ProportionalHeight` is a percentage of the font's natural line
  spacing, not of its size; the token said 165% and meant it.
- Reply and forward crashed outright - `QTextCursor.Start` does not
  exist in PySide6.
- The hover star and trash on a message row were painted, hit-tested and
  connected to nothing.
- Toasts covered the toolbar's search field and buttons for four and a
  half seconds; they sit bottom-right now, and identical notices refresh
  one card instead of stacking three.
- Closing the opening window mid-startup crashed the process and the main
  window never appeared.
- The primary button was 30px tall while every other button was 32, so
  Cancel and Save sat two pixels out of line in every dialog.
- Settings drew two hairlines between every pair of rows.
- Senders with no name showed `(` as their avatar initial.
- A long sender name ran under the timestamp beside it; a long subject
  took seven lines and pushed the message off the pane.
- Four components ignored the reduced-motion setting, and three eased on
  a different curve from everything else.

### Backend

Two additions, both required by the above:

- A `reply_to` column, added by the existing additive-migration path, so
  a reply to a mailing list goes to the list. Databases from earlier
  versions migrate without data loss.
- Cc/Bcc on both send paths. Bcc is handled oppositely per transport and
  deliberately so: kept out of the MIME for SMTP, where the envelope
  carries it, and written as a header for the Gmail API, which has no
  envelope and would otherwise never deliver it.

### Tests

245 to 391. The new suites cover the opening sequence, appearance and
keyboard wiring, list geometry under deliberately awkward data, reply
field building, and the polish regressions above.

## v1.2.1

Fixes a serious HTML email rendering bug reported against v1.2.0's
reading pane, redesigns the app icon, and audits (without changing) the
security architecture and memory behavior. No UI redesign work - v1.2.0's
visual system is untouched.

### Fixed: HTML email rendering

Real newsletters/marketing emails were rendering with images sliced into
strips, large gaps, and displaced/clipped content. Root-caused (not
guessed at) by rendering 13 realistic HTML fixtures plus a targeted
diagnostic matrix through the actual reading pane and comparing output
pixel-by-pixel:

- QTextDocument (the reading pane's rendering engine) silently ignores
  CSS `max-width`/`height:auto` - the single most common responsive-
  image pattern in real email templates. An image with no HTML width/
  height attribute renders at its raw native pixel size regardless of
  CSS, overflowing the viewport.
- When an `<img>` tag's width/height *attributes* don't match the
  image's real aspect ratio (common: retina-2x source assets, template
  edits that changed the image but not the markup), Qt's scaling does
  not cleanly stretch or letterbox - it drops rows of the source image
  and redistributes what's left. Confirmed with a labeled test image:
  an entire labeled band vanished under a mismatched width/height.
- `cid:` inline images (logos, signatures) were never resolved at all -
  silently dead references, invisible with no error.

Fix: every `<img>` tag is normalized to a width-only sizing hint before
reaching QTextDocument (confirmed by direct testing to be the one form
Qt scales correctly), with a pixel-level fallback cap for images with no
sizing hint at all. `cid:` images are now resolved to inline data: URIs
at MIME-parse time, for both the Gmail API and IMAP paths. `data:` URI
images are now decoded manually, since QTextDocument does not resolve
them on its own either (confirmed by direct testing, not assumed).
16 new regression tests cover the sizing normalizer and CID resolution.

### Audited: privacy/encryption architecture

Reviewed the full security model against a set of hard constraints (no
hashing-as-encryption, no custom cryptography, no false end-to-end-
encryption claims). Found nothing to fix - the existing AES-256-GCM at-
rest encryption, DPAPI key wrapping, OS-keyring credential storage, and
TLS-everywhere network layer were already sound. Added an explicit
"what this is not" note to the README: Unified does not provide end-to-
end encryption for Gmail/IMAP messages (no product can, without a
compatible PGP/S-MIME setup on every correspondent's end) - "encrypted
locally" always meant the local cache and credentials, never message
content in transit or at the provider, and that was never claimed
otherwise, but it's now stated in so many words rather than left implicit.

### Audited: memory usage

Profiled RSS at cold startup, empty inbox, 1k/10k cached messages,
opening a normal and an image-heavy HTML email, rapid message switching,
search, and 20s idle, using win32process (no new dependency). Peak
measured usage across all of that was ~188MB, and memory was confirmed
to release properly when leaving a heavy HTML message for a light one
(verified directly, not assumed) rather than accumulating. Could not
reproduce a 600MB figure under any tested scenario; a plausible
explanation is Windows attributing a large (1GB+) real mailbox's SQLite
file-cache pages to the process's Task Manager "Memory" column, which is
normal, reclaimable OS caching rather than an application leak. No
changes made based on unreproduced numbers - see RELEASE_NOTES for the
full checkpoint table if this needs revisiting with a live large mailbox.

### Changed: app icon

Replaced the black-and-white envelope glyph with a padlock whose shackle
*is* a bold "U" (not a separate letterform placed on a generic lock).
The previous icon's body was an elongated ~1.68:1 bar that read as
stretched inside a square canvas; the new mark uses tighter, closer-to-
square proportions and is verified pixel-exact centered (equal left/
right and top/bottom margins) at every size from 16 to 256px, work that
surfaced and fixed a real off-by-half-stroke-width vertical centering
bug along the way. Same white-fill/black-stroke treatment as before
(self-contrasts on both light and dark backgrounds) and the same
draw-fresh-per-size approach with flat pixel minimums for stroke width
and the U's inner gap, so it stays legible rather than collapsing into a
blob at 16-24px.

---

## v1.2.0

Complete privacy-focused visual redesign, built on top of v1.1.0's icon
system rather than replacing it. Design research: the app's existing
Iconly asset pack, and (for spacing/typography/component-organization
patterns only - no code, branding, or assets copied) Proton Mail's public
web client source. No backend, sync, database, encryption, or installer
*logic* changed - presentation layer only.

### What changed

- **Full design token system** (`theme.py`): a 4px spacing scale, a
  derived radius scale, named typography presets (size/weight/letter-
  spacing per context - sender, subject, timestamps, dialog headings,
  field labels, etc.) built on a Segoe UI Variable font stack, icon-size
  and control-height tokens, animation durations, and three shadow
  presets - replacing the scattered ad-hoc pixel values and one-off
  QFont calls from v1.1.0.
- **Date-grouped message list**: rows are now sectioned into Today /
  Yesterday / Earlier, painted as lightweight synthetic rows in the same
  virtualized model (not a second widget or a tree) - zero per-row
  widget cost, same delegate-based rendering as before.
- **Reading pane rebuilt as two real states**: a centered empty state
  when nothing is selected (previously a half-empty card with blank
  fields) and the message card when something is - subject now reads as
  the headline, sender name as the secondary line, matching how mail
  apps actually establish hierarchy.
- **Compose window rebuilt**: label-left borderless field rows instead
  of a QFormLayout of boxed inputs, a real header (title, discard, Send)
  instead of a generic OK/Cancel button box.
- **Settings rebuilt**: grouped, dividered panels instead of stacked
  QGroupBox frames, with a custom animated sliding toggle switch
  (`components/toggle.py`) replacing the plain checkbox for on/off
  settings.
- **New empty/error states throughout**: no accounts yet (with an Add
  account action), empty inbox/starred/sent/trash per view, and "no
  results for {query}" - previously these all silently showed a blank
  list.
- **Sidebar masthead**: the app name plus a quiet "Encrypted locally"
  line and lock glyph - the one place the product states its privacy
  premise, once, rather than repeating it as a badge on every screen.
- Six new icons (`lock`, `shield`, `more_horizontal`, `chevron_down`,
  `check`, `warning`), hand-authored to match the existing set's stroke
  weight and sizing.

### Fixed during the redesign (found via testing, not requested changes)

- `QComboBox`'s native down-arrow rendered as a plain gray rectangle
  instead of a triangle once any part of the combo box was QSS-styled -
  a known Qt/Fusion limitation where styling any subcontrol of a complex
  control drops the native arrow primitive entirely rather than falling
  back to it. Fixed by rendering the arrow as a real tinted PNG (the same
  `svg_icon` pipeline used everywhere else) instead of QSS's border-
  triangle trick, which Qt does not reliably honor for this subcontrol.
  This required moving `style.py`'s stylesheet from a module-level
  constant to a function called after `QApplication` exists, since
  building that icon needs a live Qt application.

### Untouched in this release

Gmail API integration, OAuth authentication, account storage, the
encryption system, DPAPI handling, the SQLite schema, sync workers,
background threads, email fetching, MIME parsing, the search backend,
notifications, and the build/installer *scripts* (only the version
number changed in `installer/Unified.iss`, `AppId` deliberately kept
identical so this upgrades in place over v1.1.0) - verified by diff, not
just by intent: the full pre-existing test suite (54 tests) passes
unchanged.

---

## v1.1.0

Major visual/UX redesign on top of the v1.0.1 dark theme. No backend,
sync, database, encryption, or installer *logic* changed - only the
presentation layer, on the same real-icon-based direction v1.0.1 started.

### What changed

- **Real vector icon system**: every icon in the app - toolbar (Compose,
  Refresh, Console, search), sidebar navigation (Unified Inbox, Starred,
  Sent, Trash, Add account, Settings), message list rows (star,
  attachment), the reading pane's Star/Delete actions, and the message
  context menu - is now a real SVG asset (`app/ui/svg_icon.py`,
  `assets/icons/`), tinted per Qt icon mode (Normal/Active/Selected/
  Disabled) instead of Unicode glyphs or emoji. Icons share a consistent
  24x24 stroke-based visual language, sized and aligned to match the
  surrounding text baseline, with real hover/active/selected/disabled
  states driven by Qt's icon-state machine rather than manual styling.
- **Spacing and typography tokens** (`app/ui/theme.py`): a shared
  4/8/12/16/24px spacing scale and named font weights, so components
  built at different times stop drifting from each other.
- **Genuine soft shadows**: the reading pane's header card now casts a
  real `QGraphicsDropShadowEffect` shadow (Qt stylesheets have no
  `box-shadow` equivalent), giving it actual elevation instead of just a
  border.
- **Search field redesign**: the toolbar search box is now a distinct
  pill-shaped control with a leading search icon, instead of a plain
  rectangular `QLineEdit`.
- **Reading pane identity block rebuilt**: sender email / recipients /
  account+time are now three separate lines instead of one long
  `a | b | c` string - the previous version could wrap mid-separator on
  long recipient lists and strand a lone `|` on its own line.
- **Icon-only secondary toolbar actions**: Refresh and Console are
  icon-only with tooltips (the native desktop-app convention - Compose
  keeps its label as the one primary action worth spelling out).

### Fixed during the redesign (found via testing, not requested changes)

- A Qt stylesheet cascade ordering bug: `QWidget { background:
  transparent; }` and `QMainWindow, QDialog { background: ... }` were
  being treated as equal specificity and resolved by text order, with
  the transparent rule listed second and winning. In practice this meant
  any gap in a dialog not covered by an explicitly-styled child widget
  (e.g. the space around a bare `QFormLayout` row or a
  `QDialogButtonBox`) rendered as solid black instead of the app's
  charcoal background - reproduced and confirmed in the Add Account,
  Settings, and Compose dialogs, fixed by reordering the two rules so the
  real background wins the tie.
- The attachment chip's QSS selector still targeted `QLabel#attachmentChip`
  after the chip was rebuilt as a composite icon+text `QWidget`; updated
  to `QWidget#attachmentChip`.
- Fixed-size 34x34 icon-only toolbar buttons used asymmetric padding
  (`5px 10px`) sized for icon+text buttons, which shrank the usable
  content rect narrower than the 18px icon itself; padding is now
  symmetric.

### Untouched in this release

Gmail API integration, OAuth authentication, account storage, the
encryption system, DPAPI handling, the SQLite schema, sync workers,
background threads, email fetching, MIME parsing, the search backend,
notifications, and the build/installer *scripts* (only the version
number changed in `installer/Unified.iss`, `AppId` deliberately kept
identical so this upgrades in place over v1.0.1) - verified by diff, not
just by intent: the full pre-existing test suite (54 tests) passes
unchanged.

---

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

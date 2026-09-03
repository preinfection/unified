# Unified

## v1.3.0

A full UI/UX redesign. The product does the same things it did in v1.2.1
and does them behind a new design system, a rebuilt shell, and a set of
workflows the old interface simply did not have.

### A design direction, not just a system

The palette is a **warm neutral ground with a cool accent** in both
themes. The reflex answer for a dark desktop tool - a cool grey-blue
near-black with a blue accent - is what every generated "modern dark
mode" ships, and it is what v1.2.1 was. Shifting the neutrals warm puts
the field in tension with the accent, so the accent reads as chosen
rather than as the only colour present; in light it makes the theme paper
rather than office white, which is the right material for a surface that
is almost entirely text. Neither theme uses pure black or white anywhere.

Surfaces are **material**, not flat fills with a grey outline: a raised
control catches light along its top edge and shades toward the ground
below it.

### One icon system

All 47 icons were redrawn from zero on a single grid - 24px box, 18px
live area, one 1.75 stroke, round caps and joins, optical rather than
geometric sizing. The previous set was two generations mixed together at
four different stroke widths, which is why it read as messy at the 16px
the UI actually renders it at. Four glyphs that duplicated another or
never resolved at small sizes are retired. The app mark is now a solid
tile with the envelope flap knocked out, because a thin-stroked outline
turns to mush at 20px.

### A real motion language

Qt Style Sheets have no `transition`, which is why a stylesheet-driven Qt
app feels dead: every hover, press and selection is an instant swap.
`app/ui/design/motion.py` ports the [transitions.dev](https://transitions.dev)
token set to Qt and layers Apple's fluid-interface rules on top - respond
on press, animate from the presentation value so an interrupted gesture
is picked up rather than snapped, exits faster than entrances except
where the motion is symmetric.

What that turned into:

- Buttons paint themselves: press scales to 0.972, hover arrives over
  130ms, and the focus ring is drawn outside the rect so tabbing along a
  row moves nothing.
- A **sliding indicator** in the sidebar and the message list: one marker
  that travels between rows rather than two marks blinking.
- Icon swap with real blur (the star filling in, the appearance mode
  changing), toast rise-and-scale, modal and dropdown open/close
  asymmetry, page side-by-side for the narrow layout, a skeleton shimmer
  sweep, number pop-in on unread counts, error shake on an invalid
  compose field, card resize on the sidebar collapse, and a staggered
  reveal when a message opens.
- All of it routed through one reduced-motion check, so the OS setting
  collapses every duration to zero.

### Typography that has a hierarchy again

A Qt stylesheet's font declarations override every `QFont` set in code,
so the `* { font-size: 13px }` rule was silently flattening the entire
ramp: every heading, subject line and dialog title rendered at 13px. The
base font is now installed with `QApplication.setFont()`. The ramp also
widens past the dense-metadata cluster (11/12/13/15/18/22/28), so a
subject line is 22px against 13px body, and sizes at or above 17px use
Segoe UI Variable Display - the optical cut Windows ships for them.

### A real design system

Every color, size, radius, duration and type style now comes from one
place (`app/ui/design/`), and widgets ask for them by *role* rather than
by value.

- **Semantic color roles** with two palettes behind them. Elevation runs
  sidebar -> message list -> reading pane in both themes, so the pane
  structure reads even with every border removed.
- **Accent is split in two**: a hue family for indicators, focus and
  selection tints, and a solid family for filled controls that is tuned
  for 4.5:1 against its own label. Conflating the two is how a blue
  button ends up with an unreadable white label.
- **One stylesheet**, rendered from tokens, that raises on an unknown
  placeholder instead of silently dropping the rule it appears in.
- **A live token facade**: a hand-painted delegate reading
  `t.TEXT_PRIMARY` inside `paint()` is simply correct after a theme
  change, with no invalidation protocol.
- **Measured contrast.** Every foreground/background pairing the app
  actually renders is listed with a minimum ratio and asserted by test,
  in both themes.

See `DESIGN.md` for the whole system.

### Light theme

A real light palette, not the dark one inverted - light UI takes more of
its structure from borders and less from fills, and its surfaces sit
closer together. The app follows the Windows light/dark setting by
default, and switches live: the palette, the QPalette (which covers
everything QSS cannot reach) and the stylesheet all move together.

### A rebuilt shell

- A **command bar** replaces the old QToolBar: app identity, Compose as
  the one filled button in the window, sync, search, appearance, console
  and an overflow menu.
- The **sidebar** now separates places (mailboxes) from filters
  (accounts). Previously a folder and an account both looked like a
  selected pill, which made "Inbox, filtered to this account" and "this
  account's inbox" visually identical.
- The **message list has its own header**, stating where you are, what it
  is filtered to and how many messages there are. "Showing 100 of 8,412"
  is now said out loud instead of inferred.
- The **reading pane** lost its card: the message body sits directly on
  the pane, with the subject as a real heading, expandable recipients, an
  absolute timestamp, and actions grouped by consequence - reply and
  forward on the left, destructive separated on the right.

### New in the interface

- **Reply, Reply all and Forward**, quoting the original the way a mail
  client should, with the cursor above the quote.
- **Cc and Bcc**, hidden until asked for. (Bcc is an envelope-only
  recipient over SMTP, so a blind copy is never disclosed in the headers.)
- **An unread filter** and **Mark all as read**.
- **List density** - Compact, Cozy or Relaxed.
- **Keyboard shortcuts** for every frequent action, including `J`/`K`
  navigation, `R`/`Shift+R`/`F`, `S`, `U`, `Del`, `Ctrl+1..4` and `/` for
  search.
- **A responsive shell**: below 1080px the sidebar becomes an icon rail;
  below 900px the reading pane takes over the list's space with a Back
  button.
- **Designed empty, loading and error states**, each saying what happened
  and offering the next action, with technical detail kept available
  rather than led with.
- **Dialogs in the product's own language** - `QMessageBox` is gone.

### Fixed

- **Read and unread rows now share one left edge.** The unread dot was
  inline, so every unread sender name sat 10px right of every read one
  and a mixed list went ragged down the middle. It has its own gutter.
- **Avatar colors are stable across launches.** They were derived from
  `hash()`, which is salted per process, so the same correspondent got a
  different color every time the app started.
- **Subject and preview no longer share one elision.** They were joined
  into a single string, so a long subject silently ate the preview.
- **Custom widget surfaces actually paint.** Qt draws no stylesheet
  background *or border* for a user-defined QWidget subclass without
  `WA_StyledBackground`, which is why several surfaces had no visible
  boundary.
- **Disabled danger and link buttons look disabled**, and an icon-only
  primary action keeps its fill.
- **The status strip shows one string.** `QStatusBar.showMessage()`
  paints over permanent widgets rather than replacing them, so two were
  drawn on top of each other.
- **Empty and error copy no longer overlaps** the text below it.
- **Toasts moved to the bottom-right**, clear of the reading pane's
  action row.

### Accessibility

- Keyboard focus rings that appear for Tab and shortcut focus but not for
  a mouse click, and that do not move the layout.
- Every icon-only control carries a tooltip and an accessible name,
  enforced by test.
- Reading order tab order, accessible names on the panes, and an
  accessible description per message row.
- The OS reduced-motion preference is read once and honored everywhere.
- Nothing is communicated by color alone.

### Performance

- The message-row delegate no longer builds five QFonts and three
  QFontMetrics per row per frame; they are cached and rebuilt only on a
  theme or density change.
- Elevation prefers surface contrast over `QGraphicsDropShadowEffect`,
  which is now used only on surfaces that genuinely float and never on a
  scrolling view.

### Backend

Deliberately minimal, and only where the interface required it: Cc/Bcc on
both send paths, `unread_only` filtering and `mark_all_read` in the
database layer, and two appearance settings. Sync, authentication,
encryption, the attachment guard and the HTML renderer are unchanged.

### Tests

250 pass, up from 227. `tests/test_design_system.py` was rewritten to
assert the system's *contract* - ordered and distinguishable elevation,
ordered and restrained radii, WCAG AA on every rendered pairing in both
themes, no unresolved tokens, no hardcoded colors outside the design
package, real rendered pixels for the components - rather than equality
with the external visual reference this release replaces.

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

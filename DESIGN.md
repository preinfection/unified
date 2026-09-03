# Unified — design system

This is the reference for how Unified looks and behaves, and the rules
that keep it consistent as it changes. It describes what is actually in
the code (`app/ui/design/`), not an aspiration.

---

## 1. What the product is trying to feel like

A serious, fast, quiet desktop mail client.

Mail is a working tool people keep open all day, scanning far more than
they read. Every decision below follows from that:

| Principle | What it means in practice |
|---|---|
| **Density with air** | The message list is dense because scanning matters. The reading pane is spacious because reading matters. Neither borrows the other's rules. |
| **Hierarchy through weight and space** | Emphasis comes from type weight, alignment and spacing before it comes from color, and from color before it comes from a box. |
| **Restraint** | One accent color. One filled button per screen. Cards only where things genuinely group. |
| **Say the true thing** | "Showing 100 of 8,412" beats hiding the number. An indeterminate bar beats a fake percentage. |
| **Desktop-native** | Real keyboard shortcuts, real focus, real context menus, a window that changes shape when it gets narrow. |

What it deliberately is **not**: a web dashboard, a card grid, a
glassmorphism demo, or a field of pills.

---

## 2. Architecture

```
app/ui/design/
  tokens.py        dimensional scales - spacing, radii, type, motion, geometry
  palette.py       semantic color roles + the light and dark palettes
  theme.py         ThemeManager: active palette, density, reduced motion
  stylesheet.py    the single application QSS, rendered from tokens

app/ui/theme.py    the facade every widget imports as `t`
app/ui/style.py    get_stylesheet() - what QApplication is given
```

Three rules hold this together:

1. **Widgets never name a color.** They ask for a role. The one place a
   hex value may appear is `palette.py`. A test (`test_widgets_do_not_hardcode_colors`)
   fails the build if one appears anywhere else.
2. **There is one stylesheet.** Components express intent through dynamic
   properties (`variant`, `size`, `shape`, `tone`, `role`, `state`) and
   the stylesheet decides what that looks like. Local `setStyleSheet`
   calls with literal colors are also a test failure.
3. **Color lookups are live.** `app/ui/theme.py` resolves color names
   through a module `__getattr__`, so a delegate that reads
   `t.TEXT_PRIMARY` inside `paint()` is correct on its next repaint after
   a theme change — no invalidation protocol, nothing to remember to wire
   up.

### Theme switching

`ThemeManager.apply()` does three things in order: swaps the active
`Palette`, rebuilds and installs a `QPalette` (which covers everything
QSS cannot reach — text cursors, editor selection, the disabled color
group), and re-renders the stylesheet. Rasterized icons do not follow a
palette swap by themselves, so the window walks its tree once per switch
and re-tints them (`refresh_button_icons`).

---

## 3. Color

Roles are named for **what a color is for**, never for what it looks
like. `palette.py` is the full list; the shape of it:

**Surfaces** — elevation runs *outward from the navigation*, in both
themes: the sidebar is the most recessed surface, the message list sits
above it, and the reading pane is the brightest. That gradient tells a
first-time user which pane is chrome and which is content without a
single label.

```
sidebar  →  canvas  →  surface  →  surface_hover  →  surface_active  →  overlay
```

**Text** — `text_primary`, `text_secondary`, `text_tertiary`,
`text_disabled`, `text_on_accent`, `text_link`. Each step must be
measurably distinct from the next; a test asserts the ordering and a
minimum separation.

**Accent** — two families, because conflating them is how "blue button
with an unreadable white label" happens:

- `accent`, `accent_hover`, `accent_pressed`, `accent_subtle`,
  `accent_fg` — the *hue*: indicators, focus, selected-row tints. Never
  carries text on top of it.
- `accent_solid`, `accent_solid_hover`, `accent_solid_pressed` — filled
  controls that carry `text_on_accent`, tuned for 4.5:1 against white.

**Status** — `info`, `success`, `warning`, `danger`, each with a
foreground and a subtle background, plus `danger_strong` for a
destructive button fill. Status is never communicated by color alone:
every status surface carries an icon or words as well.

**Domain** — `star` (the one non-semantic hue), `unread`, and a set of
six to eight muted `avatar_hues`.

### Contrast

`CONTRAST_CONTRACT` in `palette.py` lists every foreground/background
pairing the app actually renders, with a minimum ratio: 4.5:1 (WCAG AA)
for body text, 3.0:1 for large text and for transient interaction
surfaces. `test_contrast_contract_holds` measures every pairing in both
themes. Adding a role means adding its pairing.

### Dark is not "black everywhere"

The dark palette is a neutral graphite, not a blue-black: a strongly
tinted dark theme reads as a skin rather than a product, and it fights
every message body rendered next to it. The light palette is not the dark
one inverted — light UI takes more of its structure from borders and less
from fills, and its surface steps sit closer together.

---

## 4. Typography

A Windows-first system stack: Segoe UI Variable Text → Segoe UI → Inter →
Arial. Roles are named for the job the text does:

| Role | Size / weight | Used for |
|---|---|---|
| `display` / `title` | 24 / 19, semibold | Message subject, splash |
| `heading` / `subheading` | 16 / 14, semibold | Dialog titles, pane headers |
| `body` / `body_strong` | 13, regular / semibold | Message text, field values |
| `body_sm` | 12, regular | Secondary detail |
| `caption` | 11, regular | Metadata, status |
| `overline` | 10, bold, +0.9 tracking | Section labels |
| `sender` / `sender_read` | 13, semibold / regular | The unread signal in the list |
| `subject` / `subject_read` | 12, semibold / regular | |
| `preview` | 12, regular | Snippet |
| `timestamp` | 11, regular | |

Unread mail is **heavier** than read mail — that weight difference is the
single most important typographic signal in the product, and a test
enforces it. Read rows drop to secondary text rather than changing hue.

---

## 5. Spacing, shape and size

**Spacing** — a 4px base with two half-steps for optical corrections
inside small controls: `0, 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48`.
Nothing in layout code uses a number that is not on this ramp.

**Radii** — deliberately restrained, and ordered:

```
XS 4   chips, checkboxes, menu items, indicator bars
SM 6   buttons, inputs, list rows, dropdown options
MD 8   navigation items, menus, toasts, panel bodies
LG 10  cards, grouped setting panels
XL 12  dialogs, popovers
PILL   count badges and the search field - things that are truly round
```

`RADIUS_SM <= 6` and `RADIUS_LG <= 12` are enforced by test. Pill shape
is reserved for badges and search; a button is never a pill.

**Controls** — 22 / 26 / 30 / 34px heights; icons 12 / 14 / 16 / 20 / 24;
avatars 24 / 30 / 40.

**Shell** — sidebar 248px (56px collapsed), command bar 48px, list header
40px, reader header 44px, status strip 26px.

---

## 6. Components

Every component lives in `app/ui/components/`. The rule that shapes all
of them: **start from a real Qt control**. A painted clickable `QWidget`
loses keyboard activation, focus, `setDefault`, the accessibility tree
and platform behavior, and then has to reimplement all of it badly.

| Component | Notes |
|---|---|
| `buttons.py` | One `QPushButton`; appearance is the `variant` property: `primary`, `secondary`, `subtle`, `danger`, `danger_quiet`, `link`. `shape="icon"` makes it square and label-less. |
| `dialog.py` | `AppDialog` — one anatomy (heading, body, footer), fixed button order, Enter/Esc, destructive actions separated. `confirm` / `notify` / `report_error` replace `QMessageBox`. |
| `states.py` | `EmptyState`, `ErrorState`, `LoadingState`, `SkeletonList`. |
| `email_list.py` | Virtualized `QListView` + painted delegate; date-group headers are synthetic rows in the same flat model. |
| `reader.py` | The reading pane: no card, no elevation around the body. |
| `command_bar.py`, `list_header.py`, `sidebar.py`, `nav_pill.py` | The shell. |
| `avatar.py`, `badge.py`, `dropdown.py`, `search_field.py`, `toggle.py`, `toast.py`, `focus.py` | Primitives. |

### Where cards are, and are not, used

Cards mean "these are alternatives to compare" or "this is a grouped
settings panel". They are used for the provider choice in Add Account and
for settings groups. They are **not** used for email rows, folders,
individual settings, toolbar actions, or the message body. An inbox
should read like an inbox, not a dashboard.

---

## 7. Interaction states

Styling a rest state is not a finished component. Every interactive
control answers: rest, hover, pressed, focus, selected/checked, disabled
— plus invalid for inputs and busy for anything with in-flight work.

- **Selection is always expressed twice.** A tinted fill *and* a painted
  accent bar. Fill alone reads as hover at a glance, which is the
  difference between "the pointer is here" and "this is what you are
  reading".
- **Focus is keyboard-aware.** `components/focus.py` tags the focused
  widget with `kbfocus` only when focus arrived by Tab, Backtab, a
  shortcut or the menu, and the stylesheet turns that into a 2px ring.
  The extra border pixel is paid for out of the padding so nothing on the
  row moves.
- **Disabled stays legible.** Reduced contrast, never near-invisible
  opacity.
- **Status is never color alone.** Every status dot carries text; every
  status banner carries an icon and a sentence.

The component gallery in `.design-research/gallery.py` renders every
control in every state in both themes on one sheet — the fastest way to
find a state nobody styled.

---

## 8. Motion

Four durations, each with a job: 80ms press, 120ms hover/focus, 180ms
selection and content swaps, 280ms panels and dialogs. Nothing is longer
than 280ms; past that the UI is making the user wait to watch an
animation.

Motion is used where it communicates: the navigation indicator grows
rather than appearing, dropdowns settle into place, toasts slide in.
It is not used on list scrolling, pane resizing or anything on the
critical path of reading mail.

**Reduced motion** is read from the OS (Windows' "Show animations"
setting) once, in `ThemeManager`. Components call `t.duration(base)`,
which returns 0 when the user has asked for less motion — so the state
still changes, it just does not travel.

---

## 9. Responsive behavior

Two thresholds, each a real Qt constraint rather than a number borrowed
from CSS — the width below which a pane can no longer show its content:

- **< 1080px** — the sidebar collapses to a 56px icon rail. Labels and
  the account list drop; icons and their tooltips stay. `Ctrl+B` toggles
  it manually at any width, and a manual choice survives later resizes.
- **< 900px** — the reading pane takes over the list's space entirely,
  with a Back button. Two 300px panes side by side show nothing useful in
  either.

Long values elide rather than clip, and always elide toward the end that
matters: account addresses elide from the *left* (`…@example.com`),
because when two accounts share a provider the distinguishing part is the
local part.

---

## 10. Accessibility

- Every icon-only control has a tooltip **and** an accessible name; a
  test enumerates them and fails on an unnamed one.
- Keyboard focus is visible, ordered (`setTabOrder` follows reading
  order), and never removed for a cleaner screenshot.
- Contrast is measured, not assumed — see §3.
- Nothing is communicated by color alone.
- The message list model exposes `AccessibleTextRole`, so a screen
  reader hears "Unread message from …, subject …, Tue 4 March at 09:14"
  rather than nothing.
- Keyboard shortcuts cover every frequent action, and no action is
  *only* reachable by shortcut.

---

## 11. Performance

- The message list is virtualized: no widget per row, at any mailbox
  size.
- The row delegate's fonts and font metrics are built once and cached at
  module level, rebuilt on theme/density change — not per row, per frame.
- `QGraphicsDropShadowEffect` is used only on surfaces that genuinely
  float (menus, dialogs, toasts) and never on a scrolling view, where it
  forces the whole subtree through a software raster path every repaint.
- Sync progress reloads are coalesced to at most one per 700ms, and a
  reload scoped to one account skips re-querying a list showing a
  different one.
- Elevation prefers surface contrast, which costs nothing, over shadows.

---

## 12. Changing this system

- Add a **color** by adding a role to `Palette`, filling it in for both
  themes, and adding its pairing to `CONTRAST_CONTRACT`.
- Add a **component** in `app/ui/components/`, built on a real Qt
  control, expressing appearance through dynamic properties.
- Add a **style** by adding a selector to `stylesheet.py`. If you find
  yourself calling `setStyleSheet` in a widget, that is the signal that
  the system is missing something — add it to the system instead.
- Run `pytest tests/test_design_system.py` — it will tell you if the
  contract broke.

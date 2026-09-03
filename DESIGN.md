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

### The direction: warm ground, cool accent

Both palettes are built on a **warm neutral ground with a cool accent**,
and that is the decision carrying the product's identity.

The reflex answer for a dark desktop tool is a cool grey-blue near-black
with a blue accent. It is also what every generated "modern dark mode"
ships (zinc surfaces, white-at-10% hairlines, one unchosen blue) and it is
what this app used to be. Shifting the neutrals warm (hue near 35 degrees,
chroma low enough that nobody would call it brown) puts the whole field in
tension with the cool accent, so the accent reads as *chosen* rather than
as the only colour present. In light, it makes the theme paper rather than
office white, which is the right material for a surface that is almost
entirely text.

Neither theme uses pure black or pure white anywhere, including the toast,
which is the one deliberately inverted surface in the product.

Roles are named for **what a color is for**, never for what it looks like.
`palette.py` is the full list; the shape of it:

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

**Material** — `highlight`, `highlight_strong` and `shadow`. Real
surfaces catch light along their top edge and cast a shadow tinted by the
ground they sit on. A flat fill with a grey 1px outline is a wireframe of
a surface, not a surface, and it was the single thing that made the
previous pass look unfinished.

**Domain** — `star` (the one non-semantic hue), `unread`, and a set of six
to eight muted `avatar_hues`.

### Contrast

`CONTRAST_CONTRACT` in `palette.py` lists every foreground/background
pairing the app actually renders, with a minimum ratio: 4.5:1 (WCAG AA)
for body text, 3.0:1 for large text and for transient interaction
surfaces. `test_contrast_contract_holds` measures every pairing in both
themes. Adding a role means adding its pairing.

### Dark is not "black everywhere"

The dark palette is a warm graphite: warm enough that the field reads as
warm next to the accent, never so far that anyone would call it brown, and
never sitting at the absolute floor of the display. The light palette is
not the dark one inverted — light UI takes more of its structure from
borders and less from fills, and its surface steps sit closer together.

---

## 4. Typography

A Windows-first system stack: Segoe UI Variable Text → Segoe UI → Arial.
Sizes at and above 17px switch to **Segoe UI Variable Display**, the
optical cut Windows ships for large text: tighter spacing and finer detail
than the Text cut, which is drawn for small sizes. Using the right optical
size is a real typographic decision that costs nothing and is native to
the platform, unlike downloading whichever grotesk is currently
fashionable.

Roles are named for the job the text does:

| Role | Size / weight | Used for |
|---|---|---|
| `display` / `title` | 28 / 22, semibold | Message subject, splash |
| `heading` / `subheading` | 18 / 15, semibold | Dialog titles, pane headers |
| `body` / `body_strong` | 13, regular / semibold | Message text, field values |
| `body_sm` | 12, regular | Secondary detail |
| `caption` | 11, regular | Metadata, status |
| `overline` | 10, bold, +0.9 tracking | Section labels |
| `sender` / `sender_read` | 13, semibold / regular | The unread signal in the list |
| `subject` / `subject_read` | 12, semibold / regular | |
| `preview` | 12, regular | Snippet |
| `timestamp` | 11, regular | |

**Tracking is size-specific.** Large text tightens (-0.5px at display,
-0.2px at heading) because letterforms read too far apart as they grow;
body sits at 0. One `letter-spacing` for every size is wrong somewhere.

Unread mail is **heavier** than read mail — that weight difference is the
single most important typographic signal in the product, and a test
enforces it. Read rows drop to secondary text rather than changing hue.

> **A trap worth naming.** A Qt stylesheet's font declarations override
> every `QFont` set in code. A `* { font-size: 13px }` rule therefore
> flattens the entire ramp silently: every heading, subject line and
> dialog title renders at 13px and the hierarchy vanishes. The base font
> is installed with `QApplication.setFont()` instead, which per-widget
> fonts can still override. Never put `font-size` or `font-family` in a
> broad QSS selector.

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
| `design/motion.py` | The motion tokens and the animators every painted component uses. |

### Iconography

One system, no exceptions: a 24px box with an 18px live area, a single
**1.75 stroke**, round caps and joins, and optical rather than geometric
sizing (a circle glyph is drawn slightly larger than a square one so they
read at the same weight). Fills appear only where fullness *is* the
meaning - a filled star means starred - never as a second style. The
generator is `.design-research/make_icons.py`; regenerate rather than
hand-editing an SVG, or the set drifts back into two generations at four
stroke widths, which is exactly how the previous set became unreadable at
16px.

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

Qt Style Sheets have no `transition`. That one fact is why a QSS-styled Qt
app feels dead: every hover, press, check and selection is an instant
swap. The fix is not more animation, it is a coherent system applied from
one place, `app/ui/design/motion.py`.

### Where the values come from

The scale is the **[transitions.dev](https://transitions.dev)** token set
(Jakub Antalik) ported to Qt, rather than numbers invented here. Its
values are tuned against shipped implementations of exactly the surfaces
this app has - dropdowns, modals, toasts, sliding indicators, skeleton
reveals, icon swaps - so the app inherits an already-argued system.
Layered on top are the rules from Apple's *Designing Fluid Interfaces*,
by way of Emil Kowalski's `apple-design` skill.

| Token | Value | Used by |
|---|---|---|
| `EASE_SMOOTH_OUT` | `cubic-bezier(0.22, 1, 0.36, 1)` | opens, closes, slides, resizes |
| `EASE_IN_OUT` | symmetric | icon swap, text swap, reveals |
| `EASE_BOUNCE_STRONG` | `cubic-bezier(0.34, 3.85, 0.64, 1)` | hover-out settle |
| press / hover / state | 90 / 130 / 190 ms | interaction feedback |
| quick / fast / medium / slow | 150 / 250 / 350 / 400 ms | close / open / panel / reveal |
| stagger | 40 ms per item, 300 ms total cap | entrances |

### The rules

- **Respond on press, not on release.** Feedback starts the instant the
  pointer goes down.
- **Animate from the presentation value, never the target.** Every
  animator restarts from wherever the value currently *is*, so an
  interaction interrupted mid-flight is picked up rather than snapped.
- **Exits run at about 70% of entrances** - except where the motion is
  symmetric by nature (a travelling indicator, a page slide, an icon
  swap: the same journey either way).
- **Never animate a keyboard-repeated action.** J/K down the message list
  happens hundreds of times a day; animating it would make the app feel
  slower, not richer.
- **Motion conveys state, never decoration.** Nothing loops, nothing
  animates on load, and nothing on the critical path of reading mail
  moves at all.

### What actually animates

| Surface | Transition |
|---|---|
| Buttons | press scales to 0.972; hover arrives over 130 ms; focus ring fades in outside the rect |
| Sidebar and message-list selection | one indicator that **travels** between rows (250 ms, symmetric) |
| Star, appearance mode | icon swap: the outgoing glyph blurs and shrinks as the incoming one resolves |
| Toasts | rise 16 px with a 0.97 scale, 350 ms in / 250 ms out, same path both ways |
| Dialogs, dropdowns | open 250 ms / close 150 ms |
| Narrow-window pane change | page side-by-side: an 8 px slide in the direction of travel |
| Sidebar collapse | card resize, 300 ms |
| First sync | skeleton shimmer sweep, one cycle per 2 s |
| Unread counts | number pop-in with a slight overshoot |
| Invalid compose field | error shake, four settling segments |
| Opening a message | header lines rise, staggered 40 ms |

### Reduced motion reduces motion; it does not delete it

`ThemeManager.duration(base, spatial=...)` is the single place the policy
lives, and it makes a distinction that matters:

- **Spatial** motion moves something across the screen: a travelling
  indicator, a sliding pane, a rising toast. Under reduced motion these
  go to **zero**. That is what reduced motion is for.
- **Non-spatial** motion only changes opacity or colour in place: a
  button acknowledging a press, a hover arriving, an icon cross-fading.
  These **survive**, capped at 110ms, because they aid comprehension and
  move nothing. Removing them does not help anyone; it just makes the app
  feel broken.

**Motion is a setting** (Settings → Appearance → Motion): *Full*, *Match
Windows*, or *Reduced*, and the setting's description states what Windows
is currently asking for, because "Match Windows" is meaningless if you
cannot see what it matched.

**The default is Full, not Match Windows** - a deliberate, arguable call.
Windows' "Show animations" switch (`SPI_GETCLIENTAREAANIMATION`) is as
much a perceived-performance toggle as an accessibility one, and a great
many machines have it off for speed. Following it by default silently
deletes the entire motion design on those machines, which is exactly what
this app did before this was fixed. Unified's motion is short (nothing
over 350ms), never loops, and never blocks input, so the cost of ignoring
that switch by default is low and the cost of obeying it is the whole
design. Anyone who needs less can select *Match Windows* or *Reduced* in
one click, and both still keep the in-place feedback.

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

---

## 13. Credits

The design system is Unified's own, but two pieces of it are ported
rather than invented, and it is worth knowing where to go for the
reasoning behind them:

- **Motion tokens** — the duration, easing, distance, scale and blur scale
  in `app/ui/design/motion.py` is [transitions.dev](https://transitions.dev)
  by Jakub Antalik, ported to Qt. The per-transition behaviour (sliding
  indicator, icon swap, toast, modal, page side-by-side, skeleton reveal,
  number pop-in, error shake, card resize, texts reveal) follows that
  library's specifications.
- **Interaction rules** — respond on press, animate from the presentation
  value, interruptibility, spatial consistency, size-specific tracking:
  Apple's *Designing Fluid Interfaces* and *The Details of UI Typography*,
  by way of Emil Kowalski's `apple-design` and design-engineering
  writing.

Neither is vendored as code; both are implemented natively in Qt, because
none of the CSS mechanisms they assume (`transition`, `filter`,
`@starting-style`) exist in Qt Style Sheets.

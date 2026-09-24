# Product

## Register

product

## Users

One person, on their own Windows machine, who owns two to four mail accounts and
is tired of three browser tabs to read them. Not an enterprise seat, not a team.
The account list is theirs personally, and so is the machine.

Their context is a desk, usually evening, usually one long session rather than
constant glances. The job is: read what arrived, find the one message from four
months ago, and get out. Sending is secondary; Unified composes plain text only
and does not pretend otherwise.

The reason they picked a local client over the web is not features, it is that
the mail sits on their disk, encrypted, and works with the network off. Privacy
here is not a compliance checkbox, it is the point of the product.

## Product Purpose

Put several Gmail and IMAP accounts into one searchable inbox that works
offline, and hold the cache encrypted at rest under this Windows user only.

Success is that reading a long message and finding an old one both feel better
here than in the provider's own web client. Failure is the app drawing attention
to itself while someone is trying to read.

The security story is deliberately honest and must stay that way: the cache and
the credentials are protected, the mail itself is ordinary IMAP and the provider
can still read it. The interface may never imply end-to-end encryption.

## Brand Personality

Quiet, exact, owned.

It should feel like a private archive rather than a service: something with a
door that locks, not a dashboard that reports. Confident enough to leave space,
never chatty, never celebratory. No onboarding cheer, no empty-state jokes.

Tone in copy is plain and finished. It says what happened and stops.

## Anti-references

Inferred from the chosen direction and stated for correction:

- **Generic SaaS dark mode.** Blue accent on blue-black charcoal, identical
  rounded cards, gradient buttons. This is what v1.2.1 currently is: `theme.py`
  records that the palette was translated 1:1 from OvertimeUI's Roblox theme,
  which is where `#0b0c11` and `#60a5ff` came from. It is also the single most
  predictable answer to "dark email client", which is reason enough to leave it.
- **Gmail and Outlook web.** Dense chrome, coloured category chips, cramped
  rows, a toolbar that grows a button per feature.
- **Neon and cyberpunk.** Glow, saturated accents on pure black, sci-fi framing.
  Nothing here should look like it is powering on.
- **Stock Fluent / Windows 11 native.** Mica and acrylic and system controls.
  Unified should look deliberate, not defaulted.

## Design Principles

1. **Colour is a signal, not a surface.** Hue is reserved for things that mean
   something: sync state, an error, a starred message. Emphasis everywhere else
   is carried by luminance, weight and space. A screen with nothing wrong on it
   should be almost monochrome, so the one coloured thing is unmissable.
2. **The reading pane is a page.** The measure is capped, the leading is real,
   the type is sized to be read for minutes rather than scanned for seconds.
   Every other mail client crams here; this is where Unified is better.
3. **Recede while reading.** Chrome is quiet by default and earns contrast only
   on hover, focus, or state. Nothing pulses, glows, or moves without a reason a
   user could name.
4. **Say the true thing.** Especially about security. Plain words, no
   reassurance theatre, and never a claim the architecture does not support.
5. **One signal per state.** A selected row is selected once. Stacking a fill,
   a stripe, a colour change and a weight change on the same state is noise
   dressed as clarity.

## Accessibility & Inclusion

- Body and UI text at or above WCAG AA (4.5:1); non-text state indicators at or
  above 3:1. The old palette's tertiary text failed this and the new ramp is
  measured rather than assumed.
- Colour is never the only carrier of meaning. Sync status has a shape and a
  label as well as a hue; unread has weight as well as a dot. The semantic hues
  are chosen to stay separable under deuteranopia and protanopia, which is why
  status does not rely on a red/green pair alone.
- Motion is short and eased out, and no animation is required to understand a
  state. Respect a reduced-motion preference where Qt exposes one.
- Hit targets stay at desktop-comfortable sizes; density is bought with spacing
  and type, never by shrinking what has to be clicked.

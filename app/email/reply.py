"""Building a reply, a reply-all, or a forward from a cached message.

PURE FUNCTIONS, NO QT, NO NETWORK. Deciding who a reply goes to and how
the quoted text reads is ordinary text and address handling, and keeping
it out of the dialog means it can be tested directly against awkward
input - which is most real mail. The UI calls prepare() and gets back the
four fields a compose window needs.

WHO A REPLY ACTUALLY GOES TO, which is the part that is easy to get wrong:

  * Reply goes to Reply-To if the message carried one, otherwise to the
    sender. A mailing list that sets Reply-To is asking for exactly this
    and ignoring it is how people reply off-list by accident.
  * Reply all adds everyone the message was addressed to, MINUS the
    account that received it. Without that subtraction every reply-all
    CCs you on your own message, which is the single most common bug in
    this feature.
  * Forward addresses nobody. A forward with a prefilled recipient is one
    keystroke away from going to the wrong person.

Addresses are compared case-insensitively on the address part only:
"Ada <A@X.ORG>" and "a@x.org" are the same person, and treating them as
two is how a self-CC survives the filtering above.
"""

from __future__ import annotations

import re
from datetime import datetime

# "Name <addr@host>" or a bare "addr@host". Deliberately tolerant: this
# parses what is already in the local cache, which came from real mail and
# is not guaranteed to be well formed.
_ADDRESS = re.compile(r"<([^<>]+)>|([^\s,;<>]+@[^\s,;<>]+)")

_SUBJECT_PREFIX = re.compile(r"^\s*(re|fwd|fw)\s*:\s*", re.I)


def split_addresses(raw: str) -> list[str]:
    """Every address in a header value, in order, de-duplicated.

    Returns the full "Name <addr>" form where one was given, because a
    reply that strips display names is worse to read than one that keeps
    them.
    """
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"[,;]", raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        key = address_of(chunk).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(chunk)
    return out


def address_of(value: str) -> str:
    """The bare addr@host from "Name <addr@host>", or "" if there is none."""
    match = _ADDRESS.search(value or "")
    if not match:
        return ""
    return (match.group(1) or match.group(2) or "").strip()


def strip_prefix(subject: str) -> str:
    """Drop any number of stacked Re:/Fwd: prefixes.

    Real threads arrive as "Re: Re: Fwd: Re: the engine notes" and adding
    one more is not an improvement.
    """
    text = subject or ""
    while True:
        stripped = _SUBJECT_PREFIX.sub("", text, count=1)
        if stripped == text:
            return text.strip()
        text = stripped


def reply_subject(subject: str) -> str:
    return f"Re: {strip_prefix(subject) or '(no subject)'}"


def forward_subject(subject: str) -> str:
    return f"Fwd: {strip_prefix(subject) or '(no subject)'}"


def quote(msg: dict) -> str:
    """The quoted original, plain text, prefixed with "> ".

    Plain text because that is honestly all this product composes (see
    PRODUCT.md), and "> " because it is what every mail client on the
    other end will recognise and collapse.
    """
    body = (msg.get("body_text") or msg.get("snippet") or "").rstrip()
    sender = msg.get("sender_name") or msg.get("sender_email") or "someone"
    stamp = ""
    if msg.get("date_ts"):
        try:
            stamp = datetime.fromtimestamp(int(msg["date_ts"])).strftime(
                "%d %b %Y at %H:%M"
            )
        except (ValueError, OSError, OverflowError):
            stamp = ""
    intro = f"On {stamp}, {sender} wrote:" if stamp else f"{sender} wrote:"
    quoted = "\n".join(f"> {line}" for line in body.splitlines()) if body else "> "
    return f"\n\n{intro}\n{quoted}\n"


def forward_body(msg: dict) -> str:
    """A forwarded message keeps its own header block, because the point
    of forwarding is usually who sent it and when."""
    lines = [
        "", "", "---------- Forwarded message ----------",
        f"From: {msg.get('sender_name') or ''} <{msg.get('sender_email') or ''}>".strip(),
    ]
    if msg.get("date_ts"):
        try:
            lines.append(
                "Date: " + datetime.fromtimestamp(int(msg["date_ts"])).strftime(
                    "%d %b %Y at %H:%M"
                )
            )
        except (ValueError, OSError, OverflowError):
            pass
    lines.append(f"Subject: {msg.get('subject') or '(no subject)'}")
    if msg.get("recipients"):
        lines.append(f"To: {msg['recipients']}")
    lines.append("")
    lines.append((msg.get("body_text") or msg.get("snippet") or "").rstrip())
    return "\n".join(lines) + "\n"


def prepare(msg: dict, mode: str, account_email: str = "") -> dict:
    """Fields for a compose window: to, cc, subject, body.

    `mode` is "reply", "reply_all" or "forward". `account_email` is the
    address this message arrived at, and is excluded from the recipients
    so a reply-all never copies the sender to themselves.
    """
    if mode not in ("reply", "reply_all", "forward"):
        raise ValueError(f"unknown reply mode {mode!r}")

    subject = msg.get("subject") or ""
    if mode == "forward":
        return {
            "to": "", "cc": "",
            "subject": forward_subject(subject),
            "body": forward_body(msg),
        }

    # Reply-To wins over the sender where the message carried one.
    reply_to = (msg.get("reply_to") or "").strip()
    sender = reply_to or (
        msg.get("sender_email") or msg.get("sender_name") or ""
    ).strip()

    mine = {address_of(account_email).lower()} if account_email else set()
    mine.discard("")

    to = [a for a in split_addresses(sender) if address_of(a).lower() not in mine]

    cc: list[str] = []
    if mode == "reply_all":
        already = {address_of(a).lower() for a in to} | mine
        for candidate in split_addresses(msg.get("recipients") or ""):
            key = address_of(candidate).lower()
            if key and key not in already:
                already.add(key)
                cc.append(candidate)

    return {
        "to": ", ".join(to),
        "cc": ", ".join(cc),
        "subject": reply_subject(subject),
        "body": quote(msg),
    }

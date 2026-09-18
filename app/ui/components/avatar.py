"""Shared "initial letter in a circle" avatar painting.

Used by the sidebar's AccountItem and the email list's row delegate, so a
given address always looks the same in both places.

-------------------------------------------------------------------------
WHY THESE ARE NOT COLORED ANY MORE

They used to pick from six saturated hues (blue, teal, violet, amber,
green, mauve), hashed from the sender address. That is the conventional
answer and it was wrong here for one specific reason: this app spends hue
on meaning. Gold is starred. Red is failed. Green is synced and encrypted.
Amber is degraded. A list of ten messages was painting ten saturated
circles that meant nothing, directly beside a gold star that meant
something, and the star lost.

The circles still have to differ, because telling correspondents apart at
a glance is genuinely useful. So they differ on the axis the system has
left: LUMINANCE. Each sender gets a fixed step on the warm neutral ramp,
derived from a stable hash of their address, plus their initial. Twelve
steps is more distinguishable in practice than six hues, it survives color
blindness completely, and it leaves the star as the only saturated thing
in the row.

The hash is FNV-1a rather than Python's hash(): the built-in is salted per
process, so the same sender got a different circle on every launch. That
was a real bug in the old implementation, invisible unless you looked for
it, because nothing ever compared two runs.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter

from app.ui import theme as t

# Twelve steps between the panel and the border, so an avatar is always
# clearly a disc against the row behind it without ever being brighter
# than the sender's name sitting next to it.
_STEPS = 12
_MIN_MIX = 0.30
_MAX_MIX = 1.00


def _stable_hash(key: str) -> int:
    """FNV-1a, 32-bit.

    Deterministic across processes, unlike hash(), which Python salts per
    run unless PYTHONHASHSEED is set. An avatar that changes color when the
    app restarts is not an identity cue, it is noise.
    """
    h = 0x811C9DC5
    for byte in key.encode("utf-8", "replace"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def avatar_color(key: str) -> QColor:
    """The disc fill for a sender: a step on the warm neutral ramp."""
    if not key:
        return QColor(t.mix(t.BG_PANEL, t.BORDER_LIGHT, _MIN_MIX))
    step = _stable_hash(key.strip().lower()) % _STEPS
    amount = _MIN_MIX + (_MAX_MIX - _MIN_MIX) * (step / (_STEPS - 1))
    # Toward BORDER_LIGHT rather than toward the text color: the disc must
    # stay quieter than the name beside it, in both themes.
    return QColor(t.mix(t.BG_PANEL, t.BORDER_LIGHT, amount))


def avatar_ink(fill: QColor) -> QColor:
    """The letter color for a given disc.

    Picked by measured lightness rather than by theme, because the discs
    span a range: the same rule has to work for the darkest step in light
    mode and the lightest step in dark mode.
    """
    return QColor(t.TEXT_PRIMARY) if fill.lightness() < 128 else QColor(t.BG_APP)


def initial_letter(name: str, email: str) -> str:
    """The first letter a reader would actually call this sender's.

    SKIPS LEADING PUNCTUATION, and that is not hypothetical tidiness. The
    row delegate substitutes "(unknown)" for a message with no sender, so
    taking source[0] painted a disc containing an opening parenthesis -
    and real mail supplies plenty more: quoted display names ("Ada
    Lovelace"), addresses that arrive as <ada@example.org>, names led by a
    tag like [list]. Every one of those put a punctuation mark where an
    initial belongs.

    Falls through name, then address, then a question mark, so there is
    always exactly one character in the circle.
    """
    for source in ((name or "").strip(), (email or "").strip()):
        for char in source:
            if char.isalnum():
                return char.upper()
    return "?"


def paint_avatar(
    painter: QPainter, rect: QRectF, key: str, name: str, email: str
) -> None:
    """Paint a filled circle with a centered initial letter into rect."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    fill = avatar_color(key)
    painter.setBrush(fill)
    painter.drawEllipse(rect)

    font = QFont(painter.font())
    font.setFamilies(t.FONT_FAMILIES)
    font.setPixelSize(max(10, int(rect.height() * 0.40)))
    font.setWeight(QFont.Weight(t.WEIGHT_SEMIBOLD))
    painter.setFont(font)
    painter.setPen(avatar_ink(fill))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, initial_letter(name, email))
    painter.restore()

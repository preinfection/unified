"""The small things: shared metrics, token discipline, and awkward data.

These are the defects that make software feel almost-finished - a control
two pixels shorter than the one beside it, a radius that came from
nowhere, a subject long enough to collide with a timestamp. None of them
is visible in a code review and all of them are visible on screen, so
each one here is asserted against measured geometry or against the
stylesheet the app actually builds.
"""
from __future__ import annotations

import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from app.ui import theme as t
from app.ui.components.primitives import Button, IconButton, Variant


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet
    app.setStyleSheet(get_stylesheet())
    yield app


def _css() -> str:
    """The stylesheet with comments stripped - they discuss the values
    they forbid, and a naive search finds the explanation."""
    from app.ui.style import get_stylesheet
    return re.sub(r"/\*.*?\*/", "", get_stylesheet(), flags=re.S)


# --------------------------------------------------------- shared metrics

def test_every_button_variant_shares_one_height(qapp):
    """THE TWO-PIXEL BUG. btn-primary carried `border: none` so its fill
    could be painted rather than drawn by QSS - which also took the border
    out of the box model and made it 30px tall while every other variant
    was 32. "Cancel" and "Save" sat two pixels out of line in every dialog
    in the app.
    """
    host = QWidget()
    row = QHBoxLayout(host)
    buttons = []
    for variant in Variant:
        button = Button("Save", variant)
        row.addWidget(button)
        buttons.append(button)
    icon = IconButton("trash", "Delete")
    row.addWidget(icon)
    buttons.append(icon)
    host.show()
    qapp.processEvents()

    heights = {b.height() for b in buttons}
    assert heights == {t.HEIGHT_MD}, (
        f"button heights disagree: {sorted(heights)} (want {t.HEIGHT_MD})"
    )
    host.close()


def test_bordered_variants_with_the_same_label_are_the_same_width(qapp):
    """A Cancel/Save pair whose two halves are different widths for the
    same word is an asymmetry nobody can name and everybody sees."""
    host = QWidget()
    row = QHBoxLayout(host)
    widths = set()
    for variant in (Variant.PRIMARY, Variant.SECONDARY, Variant.DESTRUCTIVE):
        button = Button("Save", variant)
        row.addWidget(button)
        widths.add(button.sizeHint().width())
    host.show()
    qapp.processEvents()
    assert len(widths) == 1, f"same label, different widths: {sorted(widths)}"
    host.close()


# -------------------------------------------------------- token discipline

def test_every_corner_radius_comes_from_the_scale(qapp):
    """A radius that came from nowhere is the clearest sign a component
    was styled in isolation - the scrollbar handle was 4px and the
    progress chunk 2px, neither of which is a step in the system."""
    allowed = {
        t.RADIUS_XS, t.RADIUS_SM, t.RADIUS_MD, t.RADIUS_LG, t.RADIUS_XL,
        t.RADIUS_PILL, 0,
    }
    found = set()
    for value in re.findall(r"border-radius:\s*([^;]+);", _css()):
        value = value.strip()
        for part in value.split():
            if part.endswith("px"):
                found.add(int(part[:-2]))
            elif part == "0":
                found.add(0)
    stray = found - allowed
    assert not stray, f"radii outside the scale: {sorted(stray)}"


def test_no_universal_selector_sets_a_font(qapp):
    """Re-asserted here as well as in test_design_system, because this is
    the one stylesheet mistake that silently flattens the whole
    typographic scale."""
    match = re.search(r"(?<![\w#.\]])\*\s*\{([^}]*)\}", _css())
    assert match
    assert "font-size" not in match.group(1)
    assert "font-family" not in match.group(1)


def test_the_stylesheet_hardcodes_no_colours(qapp):
    """Every colour has to come from theme.py, or a theme switch leaves
    part of the window behind."""
    css = _css()
    # The wash tokens are rgba() and legitimate; what must not appear is a
    # literal hex that theme.py never produced.
    from app.ui import theme
    known = {
        v.lower() for v in vars(theme).values()
        if isinstance(v, str) and v.startswith("#")
    }
    used = {m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}\b", css)}
    stray = used - known
    assert not stray, f"hard-coded colours in the stylesheet: {sorted(stray)}"


# ------------------------------------------------------------ awkward data

AWKWARD = [
    dict(
        id=1, uid="1", account_id=1, folder="inbox",
        sender_name="Bartholomew Fitzwilliam-Cholmondeley de la Rochefoucauld III",
        sender_email="bartholomew.fitzwilliam@an-extremely-long-domain-name.example",
        subject=(
            "Re: Fwd: Re: quarterly consolidated reconciliation of the "
            "distributed ledger subsystem and its downstream dependencies, "
            "including the parts nobody has looked at since 2019"
        ),
        snippet="x" * 400,
        date_ts=1_900_000_000, is_read=0, is_starred=1, has_attachments=1,
    ),
    dict(
        id=2, uid="2", account_id=1, folder="inbox",
        sender_name="", sender_email="", subject="", snippet="",
        date_ts=0, is_read=1, is_starred=0, has_attachments=0,
    ),
    dict(
        id=3, uid="3", account_id=1, folder="inbox",
        sender_name="a", sender_email="a@b.c", subject="?", snippet="",
        date_ts=1_900_000_000, is_read=0, is_starred=0, has_attachments=0,
    ),
    dict(
        id=4, uid="4", account_id=1, folder="inbox",
        sender_name="日本語の送信者名前テストケース",
        sender_email="test@example.jp",
        subject="件名のテスト - こんにちは世界",
        snippet="これはスニペットです。",
        date_ts=1_900_000_000, is_read=0, is_starred=1, has_attachments=1,
    ),
]


@pytest.mark.parametrize("width", [1400, 900, 600, 420, 320])
def test_the_list_survives_awkward_data_at_every_width(qapp, width):
    """Long names, no subject, one-character messages, CJK. Nothing here
    may clip outside the row or produce a sideways scrollbar."""
    from app.ui.components.email_list import EmailListView

    view = EmailListView()
    view.set_rows(AWKWARD)
    view.resize(width, 500)
    view.show()
    qapp.processEvents()

    viewport = view.viewport().width()
    for row in range(view._model.rowCount()):
        rect = view.visualRect(view._model.index(row, 0))
        assert rect.width() <= viewport, f"row {row} overflows at {width}px"
    assert not view.horizontalScrollBar().isVisible()
    # And it still paints: a delegate that raises on empty fields would
    # take the whole list with it.
    view.grab()
    view.close()


def test_a_message_with_no_subject_states_the_absence(qapp):
    """An empty subject must read as a stated absence rather than as a
    blank line the reader has to interpret - and it has to say so out
    loud as well as on screen."""
    from PySide6.QtCore import Qt
    from app.ui.components.email_list import EmailListView

    view = EmailListView()
    view.set_rows([AWKWARD[1]])          # every field empty
    view.resize(800, 300)
    view.show()
    qapp.processEvents()

    index = view._model.index_of(2)
    assert index.isValid()
    announced = view._model.data(index, Qt.ItemDataRole.AccessibleTextRole)
    assert "no subject" in announced.lower()
    assert "unknown" in announced.lower(), "an empty sender announces as nothing"
    view.close()


def test_the_accessible_description_covers_every_row(qapp):
    """A custom-painted row is silent to a screen reader unless the model
    says what it is, and these are exactly the rows most likely to be
    missing fields."""
    from PySide6.QtCore import Qt
    from app.ui.components.email_list import EmailListView

    view = EmailListView()
    view.set_rows(AWKWARD)
    for row in range(view._model.rowCount()):
        index = view._model.index(row, 0)
        text = view._model.data(index, Qt.ItemDataRole.AccessibleTextRole)
        assert text and text.strip(), f"row {row} announces nothing"
    view.close()


# ------------------------------------------------------------- avatars

@pytest.mark.parametrize("name,email,expected", [
    ("(unknown)", "", "U"),
    ("Ada Lovelace", "ada@x.org", "A"),
    ('"Ada Lovelace"', "ada@x.org", "A"),
    ("<ada@example.org>", "", "A"),
    ("[list] Announcements", "", "L"),
    ("", "grace@navy.mil", "G"),
    ("", "", "?"),
    ("   ", "  ", "?"),
    ("...", "ada@x.org", "A"),
])
def test_the_avatar_initial_skips_punctuation(name, email, expected):
    """The row delegate substitutes "(unknown)" for a missing sender, so
    taking source[0] painted a disc containing an opening parenthesis -
    and real mail supplies quoted names, bare <addresses> and [tag]-led
    subjects too."""
    from app.ui.components.avatar import initial_letter
    assert initial_letter(name, email) == expected


# --------------------------------------------------------------- toasts

def test_identical_notices_do_not_stack(qapp):
    """Three accounts with an expired sign-in produce three identical
    failures within a few hundred milliseconds. Three copies of one
    sentence is not more information."""
    from PySide6.QtWidgets import QMainWindow
    from app.ui.components.toast import ToastHost

    window = QMainWindow()
    window.resize(1200, 800)
    window.show()
    qapp.processEvents()
    host = ToastHost(window)

    for _ in range(3):
        host.show("Server update failed", "No valid credentials.", kind="error")
    qapp.processEvents()
    assert len(host._toasts) == 1

    host.show("Sync complete", "2 new messages", kind="success")
    qapp.processEvents()
    assert len(host._toasts) == 2
    window.close()


def test_a_repeat_refreshes_the_notice_rather_than_ignoring_it(qapp):
    """A fault that keeps recurring keeps its card on screen."""
    from PySide6.QtWidgets import QMainWindow
    from app.ui.components.toast import ToastHost

    window = QMainWindow()
    window.resize(1200, 800)
    window.show()
    qapp.processEvents()
    host = ToastHost(window)
    host.show("Sync error", "timed out", kind="error", duration_ms=5000)
    card = host._toasts[0]
    card._dismiss_timer.stop()
    card._dismiss_timer.start(50)          # about to expire

    host.show("Sync error", "timed out", kind="error", duration_ms=5000)
    assert card._dismiss_timer.remainingTime() > 1000, (
        "the repeat did not give the card its life back"
    )
    window.close()


# ---------------------------------------------------------- reading pane

def test_a_hostile_subject_cannot_take_over_the_reading_pane():
    """A subject is untrusted input. Uncapped, a sender can push the
    attribution, the actions and the body off the pane with one header."""
    from app.ui.components.preview_pane import _SUBJECT_MAX_CHARS, _clamp_subject

    clamped = _clamp_subject("x" * 5000)
    assert len(clamped) <= _SUBJECT_MAX_CHARS + 1
    assert clamped.endswith("…")
    assert _clamp_subject("") == "(no subject)"
    assert _clamp_subject("   ") == "(no subject)"
    assert _clamp_subject("Short one") == "Short one"


def test_a_long_sender_name_elides_instead_of_colliding(qapp):
    """A 59-character display name ran under the timestamp beside it and
    collided with it outright once the pane got narrower."""
    from app.ui.components.preview_pane import PreviewPane

    pane = PreviewPane()
    pane.resize(420, 700)
    pane.show()
    qapp.processEvents()
    long_name = "Bartholomew Fitzwilliam-Cholmondeley de la Rochefoucauld III"
    pane.show_message(
        subject="Hello", sender_name=long_name,
        sender_email="b@an-extremely-long-domain-name.example",
        recipients="you@example.com", account_email="you@example.com",
        time_text="19:46", has_attachments=False, is_starred=False,
    )
    qapp.processEvents()
    qapp.processEvents()

    label = pane._sender_name
    assert label.full_text() == long_name, "the full name was lost, not elided"
    assert label.text() != long_name, "the name did not elide at 420px"
    assert label.toolTip() == long_name, "the elided name is unreachable"
    pane.close()


def test_a_long_subject_is_clamped_rather_than_taking_the_page(qapp):
    """At a 340px pane width a real subject ran to seven lines and pushed
    the attribution, the actions and the message itself off the page."""
    from app.ui.components.primitives import ClampedLabel

    subject = (
        "Re: Fwd: Re: quarterly consolidated reconciliation of the "
        "distributed ledger subsystem and its downstream dependencies, "
        "including the parts nobody has looked at since 2019"
    )
    label = ClampedLabel("", max_lines=3)
    label.setFont(t.make_font("dialog_heading"))
    label.resize(300, 400)
    label.show()
    qapp.processEvents()
    label.setText(subject)
    qapp.processEvents()

    assert label.text().endswith("…"), "clamped without saying so"
    assert len(label.text()) < len(subject)
    assert label.full_text() == subject, "the full subject was lost"
    assert label.toolTip() == subject, "the clamped subject is unreachable"

    # The DISPLAYED text is what has to fit in three lines. _line_breaks
    # deliberately measures the full string - that is how the clamp finds
    # where to cut - so laying out the shown text is the real check.
    from PySide6.QtGui import QTextLayout

    layout = QTextLayout(label.text(), label.font())
    layout.beginLayout()
    shown = 0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(300)
        shown += 1
    layout.endLayout()
    assert shown <= 3, f"the clamped subject still renders on {shown} lines"
    label.close()


def test_a_short_subject_is_left_completely_alone(qapp):
    from app.ui.components.primitives import ClampedLabel

    label = ClampedLabel("", max_lines=3)
    label.resize(400, 200)
    label.show()
    qapp.processEvents()
    label.setText("Re: the engine notes")
    qapp.processEvents()
    assert label.text() == "Re: the engine notes"
    assert label.toolTip() == "", "an untruncated label should carry no tooltip"
    label.close()


def test_the_reading_pane_header_stays_bounded_at_a_narrow_width(qapp):
    """The whole point of the two clamps together: the message must still
    have room on the page."""
    from app.ui.components.preview_pane import PreviewPane

    pane = PreviewPane()
    pane.resize(340, 700)
    pane.show()
    qapp.processEvents()
    pane.show_message(
        subject=("Re: Fwd: Re: quarterly consolidated reconciliation of the "
                 "distributed ledger subsystem and its downstream "
                 "dependencies, including the parts nobody has looked at"),
        sender_name="Bartholomew Fitzwilliam-Cholmondeley de la Rochefoucauld III",
        sender_email="bartholomew@an-extremely-long-domain-name.example",
        recipients="you@example.com, someone-else@another-long-domain.example",
        account_email="you@example.com", time_text="19:46",
        has_attachments=True, is_starred=True,
    )
    qapp.processEvents()
    qapp.processEvents()

    # The body must still get the majority of the pane.
    body_top = pane.body.mapTo(pane, pane.body.rect().topLeft()).y()
    assert body_top < pane.height() * 0.6, (
        f"the header pushed the message to y={body_top} of {pane.height()}"
    )
    pane.close()


# ------------------------------------------------------------ motion system

def test_no_component_invents_its_own_easing_curve():
    """ONE CURVE EVERYWHERE. Three components animated on OutCubic while
    the nav pill, the sidebar, the opening bar and every motion.py helper
    used OutQuint - so a toggle, a dropdown and a toast each settled
    visibly differently from everything around them.

    motion.flash is the single documented exception: a dip-and-recover
    needs to be symmetrical, and an ease-out curve makes it lopsided.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in root.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        source = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(source.splitlines(), 1):
            if "setEasingCurve" not in line or line.strip().startswith("#"):
                continue
            if "motion.curve()" in line or "curve()" in line:
                continue
            if "Linear" in line:      # a countdown is a clock, not a transition
                continue
            if path.name == "motion.py" and "InOutQuad" in line:
                continue              # flash(), documented above
            offenders.append(f"{path.relative_to(root)}:{line_no}: {line.strip()}")
    assert not offenders, "components easing differently:\n" + "\n".join(offenders)


def test_every_animated_component_honours_reduced_motion(qapp):
    """Reduced motion has to reach the components that animate themselves,
    not just the motion.py helpers. All four of these tweened regardless
    of the setting - and the dropdown and the toast were the two largest
    movements left in the product."""
    from PySide6.QtCore import QPoint
    from app.ui import motion
    from app.ui.components.nav_pill import NavPill
    from app.ui.components.toggle import Toggle

    motion.set_motion_enabled(False)
    try:
        pill = NavPill("Inbox")
        pill.setChecked(True)
        assert pill._indicator == 1.0, "the nav pill still tweened"
        pill.setChecked(False)
        assert pill._indicator == 0.0

        toggle = Toggle()
        toggle.setChecked(True)
        assert toggle._knob_pos == 1.0, "the toggle knob still slid"
        toggle.setChecked(False)
        assert toggle._knob_pos == 0.0
    finally:
        motion.set_motion_enabled(True)


def test_reduced_motion_still_places_a_toast_correctly(qapp):
    """Reduced motion must mean "arrives without travelling", never
    "arrives in the wrong place"."""
    from PySide6.QtWidgets import QMainWindow
    from app.ui import motion
    from app.ui.components.toast import ToastHost

    motion.set_motion_enabled(False)
    try:
        window = QMainWindow()
        window.resize(1200, 800)
        window.show()
        qapp.processEvents()
        host = ToastHost(window)
        host.show("Sync complete", "2 new messages", kind="success")
        qapp.processEvents()

        card = host._toasts[0]
        expected_x = window.width() - t.TOAST_WIDTH - t.TOAST_MARGIN
        assert card.x() == expected_x, (
            f"the card settled at x={card.x()}, not {expected_x}"
        )
        assert card.y() < window.height(), "the card is off the bottom"
        window.close()
    finally:
        motion.set_motion_enabled(True)


def test_animation_durations_all_come_from_the_tokens():
    """A one-off millisecond value is how one screen ends up feeling
    snappier than another."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in root.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = re.search(r"setDuration\(\s*(\d+)\s*\)", line)
            if match:
                offenders.append(f"{path.relative_to(root)}:{line_no}: {line.strip()}")
    assert not offenders, "hard-coded durations:\n" + "\n".join(offenders)

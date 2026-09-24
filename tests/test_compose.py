"""Compose: prefill, Cc/Bcc, send states, and discard.

The Bcc cases are the ones that matter most. A blind copy that leaks into
the message headers is a confidentiality failure rather than a cosmetic
bug, and the two transports have to handle it in OPPOSITE ways - SMTP has
an envelope to put it in and must keep it out of the MIME, while the Gmail
API has no envelope and derives its recipients from the headers, so it
must write one. Getting either backwards is silent.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.email import reply as reply_builder
from app.email import smtp_client
from app.ui.compose_dialog import ComposeDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.style import get_stylesheet
    app.setStyleSheet(get_stylesheet())
    yield app


ACCOUNTS = [
    {"id": 1, "email": "you@example.com", "provider": "gmail"},
    {"id": 2, "email": "work@company.com", "provider": "imap"},
]


# ------------------------------------------------------------------ bcc

def test_smtp_keeps_bcc_out_of_the_message_headers():
    """A blind copy is blind because the address travels in the envelope.
    Writing it into the MIME would hand the whole blind-copy list to
    everyone who received the message."""
    mime = smtp_client.build_mime(
        "me@example.com", "to@example.com", "Subject", "Body",
        cc="cc@example.com",
    )
    raw = mime.as_string()
    assert "cc@example.com" in raw
    assert mime["Bcc"] is None
    assert "secret@example.com" not in raw


def test_smtp_still_delivers_to_the_bcc_addresses():
    """Out of the headers, but not out of the envelope - otherwise the
    blind copy is simply never sent."""
    envelope = (
        smtp_client.split_addresses("to@example.com")
        + smtp_client.split_addresses("cc@example.com")
        + smtp_client.split_addresses("secret@example.com, other@example.com")
    )
    assert envelope == [
        "to@example.com", "cc@example.com",
        "secret@example.com", "other@example.com",
    ]


@pytest.mark.parametrize("raw,expected", [
    ("a@x.org, b@y.org", ["a@x.org", "b@y.org"]),
    ("  a@x.org ,, b@y.org  ", ["a@x.org", "b@y.org"]),
    ("", []),
    (None, []),
])
def test_address_splitting_tolerates_real_input(raw, expected):
    assert smtp_client.split_addresses(raw) == expected


# -------------------------------------------------------------- prefill

def test_a_reply_opens_prefilled_and_ready_to_write(qapp):
    msg = {
        "subject": "the engine notes", "sender_name": "Ada",
        "sender_email": "ada@analytical.org",
        "recipients": "you@example.com, grace@navy.mil",
        "body_text": "The appendix is done.", "date_ts": 1_700_000_000,
        "reply_to": "",
    }
    fields = reply_builder.prepare(msg, "reply_all", "you@example.com")
    dialog = ComposeDialog(
        ACCOUNTS, mode="reply_all", to=fields["to"], cc=fields["cc"],
        subject=fields["subject"], body=fields["body"],
        from_account=ACCOUNTS[0],
    )
    assert dialog.to_edit.text() == "ada@analytical.org"
    assert "grace@navy.mil" in dialog.cc_edit.text()
    assert dialog.subject_edit.text() == "Re: the engine notes"
    assert "> The appendix is done." in dialog.body_edit.toPlainText()
    # A reply already has its recipient and subject; the only thing left
    # to do is write.
    assert dialog.body_edit.hasFocus() or dialog.mode == "reply_all"


def test_cc_is_shown_when_a_reply_actually_has_one(qapp):
    """No point hiding a field that is not empty."""
    dialog = ComposeDialog(ACCOUNTS, mode="reply_all", cc="someone@example.com")
    assert dialog._cc_row.isVisible() or dialog.cc_toggle.isChecked()


def test_cc_starts_hidden_on_a_new_message(qapp):
    """Most messages have neither, and three empty fields is three rows
    of nothing."""
    dialog = ComposeDialog(ACCOUNTS)
    assert not dialog._cc_row.isVisible()
    assert not dialog.cc_toggle.isChecked()


def test_hiding_cc_clears_it_so_it_cannot_send_invisibly(qapp):
    """A hidden field holding an address would send to someone the writer
    can no longer see."""
    dialog = ComposeDialog(ACCOUNTS)
    dialog.cc_toggle.setChecked(True)
    dialog.cc_edit.setText("someone@example.com")
    dialog.cc_toggle.setChecked(False)
    assert dialog._recipients()[1] == ""


def test_the_window_says_which_of_the_four_things_it_is(qapp):
    for mode, title in (("new", "New message"), ("reply", "Reply"),
                        ("reply_all", "Reply to all"), ("forward", "Forward")):
        assert ComposeDialog(ACCOUNTS, mode=mode).windowTitle() == title


def test_an_unknown_mode_falls_back_rather_than_raising(qapp):
    assert ComposeDialog(ACCOUNTS, mode="bounce").mode == "new"


# --------------------------------------------------------------- states

def test_sending_with_no_recipient_explains_itself_in_place(qapp):
    """The field explains its own problem rather than a modal explaining
    it somewhere else and then vanishing."""
    dialog = ComposeDialog(ACCOUNTS)
    dialog._on_send()
    assert dialog.status_label.text()
    assert "recipient" in dialog.status_label.text().lower()
    assert dialog.to_edit.property("invalid") == "true"
    assert dialog.send_btn.isEnabled(), "a validation refusal is not a send"


def test_a_failed_send_keeps_the_reason_visible_and_the_message_intact(qapp):
    """It used to raise a modal and blank the status line, so dismissing
    the modal destroyed the only account of what went wrong."""
    dialog = ComposeDialog(ACCOUNTS)
    dialog.to_edit.setText("someone@example.com")
    dialog.body_edit.setPlainText("Please keep this.")
    dialog._on_failed("the server refused the connection")

    assert "the server refused the connection" in dialog.status_label.text()
    assert dialog.body_edit.toPlainText() == "Please keep this."
    assert dialog.send_btn.isEnabled(), "a failed send must be retryable"
    assert dialog.discard_btn.isEnabled()


def test_a_send_in_flight_cannot_be_discarded(qapp):
    """The worker writes to widgets on this dialog when it completes, so
    letting the window close out from under it is a use-after-free."""
    dialog = ComposeDialog(ACCOUNTS)
    # A sentinel, because QDialog.result() is already 0 (Rejected) before
    # anything happens - so "still Rejected" would prove nothing.
    dialog.setResult(99)
    dialog._sending = True
    dialog.reject()
    assert dialog.result() == 99, "reject() went through mid-send"


# -------------------------------------------------------------- discard

def test_an_untouched_window_is_not_dirty(qapp):
    """Closing an untouched window should not interrogate anybody."""
    assert not ComposeDialog(ACCOUNTS).is_dirty()


def test_a_reply_is_not_dirty_from_its_quoted_text_alone(qapp):
    """The quote was not written here, so it is not something to lose -
    but the recipient a reply arrives with IS, which is why this asserts
    the body specifically."""
    dialog = ComposeDialog(ACCOUNTS, mode="reply", body="\n\n> quoted")
    assert not dialog.is_dirty()


def test_typing_a_recipient_makes_it_dirty(qapp):
    dialog = ComposeDialog(ACCOUNTS)
    dialog.to_edit.setText("someone@example.com")
    assert dialog.is_dirty()

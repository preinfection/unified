"""Reply / reply-all / forward field building.

Pure functions, so these are exact rather than approximate. The cases that
matter are the ones real mail produces: stacked Re: prefixes, display
names wrapped around addresses, a Reply-To that differs from the sender,
and the account's own address sitting in the To line of the message it
received.
"""
from __future__ import annotations

import pytest

from app.email import reply


def _msg(**over) -> dict:
    base = dict(
        subject="the engine notes",
        sender_name="Ada Lovelace",
        sender_email="ada@analytical.org",
        recipients="you@example.com, Grace Hopper <grace@navy.mil>",
        body_text="I have finished the appendix.\nIt runs long.",
        snippet="",
        date_ts=1_700_000_000,
        reply_to="",
    )
    base.update(over)
    return base


# ------------------------------------------------------------- subjects

@pytest.mark.parametrize("given,expected", [
    ("the engine notes", "Re: the engine notes"),
    ("Re: the engine notes", "Re: the engine notes"),
    ("RE: re: Fwd: the engine notes", "Re: the engine notes"),
    ("", "Re: (no subject)"),
])
def test_reply_subject_never_stacks_prefixes(given, expected):
    """Real threads arrive as "Re: Re: Fwd: Re: ..." and adding one more
    is not an improvement."""
    assert reply.reply_subject(given) == expected


def test_forward_subject_uses_its_own_prefix():
    assert reply.forward_subject("Re: notes") == "Fwd: notes"


# ------------------------------------------------------------ addresses

def test_display_names_are_kept():
    """A reply that strips display names is worse to read than one that
    keeps them."""
    out = reply.split_addresses("Grace Hopper <grace@navy.mil>, ada@analytical.org")
    assert out == ["Grace Hopper <grace@navy.mil>", "ada@analytical.org"]


def test_addresses_are_deduplicated_case_insensitively():
    out = reply.split_addresses("A@X.org, Ada <a@x.ORG>, b@y.org")
    assert len(out) == 2


@pytest.mark.parametrize("given,expected", [
    ("Ada Lovelace <ada@analytical.org>", "ada@analytical.org"),
    ("ada@analytical.org", "ada@analytical.org"),
    ("no address here", ""),
])
def test_address_of_extracts_the_bare_address(given, expected):
    assert reply.address_of(given) == expected


# --------------------------------------------------------------- reply

def test_reply_goes_to_the_sender():
    fields = reply.prepare(_msg(), "reply", "you@example.com")
    assert fields["to"] == "ada@analytical.org"
    assert fields["cc"] == ""


def test_reply_prefers_reply_to_over_the_sender():
    """A mailing list that sets Reply-To is asking for exactly this, and
    ignoring it is how people reply off-list by accident."""
    fields = reply.prepare(
        _msg(reply_to="list@discuss.org"), "reply", "you@example.com"
    )
    assert fields["to"] == "list@discuss.org"


def test_reply_quotes_the_original():
    fields = reply.prepare(_msg(), "reply", "you@example.com")
    assert "> I have finished the appendix." in fields["body"]
    assert "> It runs long." in fields["body"]
    assert "Ada Lovelace wrote:" in fields["body"]


def test_reply_falls_back_to_the_snippet_when_no_body_was_cached():
    fields = reply.prepare(
        _msg(body_text="", snippet="Only a snippet survived."), "reply"
    )
    assert "> Only a snippet survived." in fields["body"]


# ----------------------------------------------------------- reply all

def test_reply_all_copies_the_other_recipients():
    fields = reply.prepare(_msg(), "reply_all", "you@example.com")
    assert fields["to"] == "ada@analytical.org"
    assert "Grace Hopper <grace@navy.mil>" in fields["cc"]


def test_reply_all_never_copies_you_to_yourself():
    """THE CLASSIC BUG IN THIS FEATURE. The account that received the
    message is in its own To line; without subtracting it, every
    reply-all CCs the sender on their own message."""
    fields = reply.prepare(_msg(), "reply_all", "you@example.com")
    assert "you@example.com" not in fields["cc"]


def test_reply_all_matches_your_address_case_insensitively():
    fields = reply.prepare(
        _msg(recipients="YOU@Example.COM, grace@navy.mil"),
        "reply_all", "you@example.com",
    )
    assert "example.com" not in fields["cc"].lower()


def test_reply_all_does_not_repeat_the_sender_in_cc():
    fields = reply.prepare(
        _msg(recipients="ada@analytical.org, grace@navy.mil"),
        "reply_all", "you@example.com",
    )
    assert fields["cc"].count("ada@analytical.org") == 0


# -------------------------------------------------------------- forward

def test_forward_addresses_nobody():
    """A forward with a prefilled recipient is one keystroke from going to
    the wrong person."""
    fields = reply.prepare(_msg(), "forward", "you@example.com")
    assert fields["to"] == ""
    assert fields["cc"] == ""


def test_forward_keeps_the_original_header_block():
    fields = reply.prepare(_msg(), "forward", "you@example.com")
    body = fields["body"]
    assert "Forwarded message" in body
    assert "ada@analytical.org" in body
    assert "Subject: the engine notes" in body


# --------------------------------------------------------------- guards

def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        reply.prepare(_msg(), "bounce")


def test_a_message_with_almost_nothing_in_it_still_produces_fields():
    """Rows written by an older build can be missing anything; a reply
    must degrade rather than raise."""
    fields = reply.prepare({}, "reply")
    assert fields["subject"] == "Re: (no subject)"
    assert isinstance(fields["body"], str)


def test_a_broken_timestamp_does_not_raise():
    fields = reply.prepare(_msg(date_ts=99_999_999_999_999), "reply")
    assert "wrote:" in fields["body"]

"""Tests for RFC 822 parsing into the app's message shape."""

from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.email.message_parser import (
    decode_header_value,
    make_snippet,
    parse_rfc822,
    resolve_cid_images,
)


def build_simple(subject="Test subject", body="Line one.\nLine two."):
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = "Alice Example <alice@example.com>"
    msg["To"] = "me@example.com"
    msg["Subject"] = subject
    msg["Date"] = "Thu, 06 Aug 2026 12:30:00 +0000"
    return msg


def test_parse_simple_message():
    raw = build_simple().as_bytes()
    parsed = parse_rfc822(raw, account_id=1, folder="inbox", uid="42")
    assert parsed["sender_email"] == "alice@example.com"
    assert parsed["sender_name"] == "Alice Example"
    assert parsed["subject"] == "Test subject"
    assert parsed["uid"] == "42"
    assert parsed["folder"] == "inbox"
    assert "Line one." in parsed["body_text"]
    assert parsed["date_ts"] > 0
    assert parsed["has_attachments"] == 0
    assert parsed["snippet"].startswith("Line one.")


def test_parse_multipart_with_attachment():
    msg = MIMEMultipart()
    msg["From"] = "bob@example.com"
    msg["To"] = "me@example.com"
    msg["Subject"] = "With attachment"
    msg.attach(MIMEText("plain part", "plain"))
    msg.attach(MIMEText("<p>html part</p>", "html"))
    attachment = MIMEBase("application", "octet-stream")
    attachment.set_payload(b"1234")
    attachment.add_header(
        "Content-Disposition", "attachment", filename="data.bin"
    )
    msg.attach(attachment)

    parsed = parse_rfc822(msg.as_bytes(), account_id=1, folder="inbox", uid="7")
    assert parsed["has_attachments"] == 1
    assert parsed["body_text"] == "plain part"
    assert "<p>html part</p>" in parsed["body_html"]


def test_encoded_header_decoding():
    encoded = "=?utf-8?B?SMOpbGxvIFfDtnJsZA==?="
    assert decode_header_value(encoded) == "Héllo Wörld"


def test_read_and_star_flags():
    raw = build_simple().as_bytes()
    parsed = parse_rfc822(raw, 1, "inbox", "1", is_read=True, is_starred=True)
    assert parsed["is_read"] == 1
    assert parsed["is_starred"] == 1


def test_snippet_from_html_when_no_text():
    snippet = make_snippet("", "<div>Hello  <b>world</b></div>")
    assert snippet == "Hello world"


def test_unparseable_date_defaults_to_zero():
    msg = build_simple()
    del msg["Date"]
    msg["Date"] = "not a date"
    parsed = parse_rfc822(msg.as_bytes(), 1, "inbox", "9")
    assert parsed["date_ts"] == 0


# --------------------------------------------------------- inline CID images

def test_resolve_cid_images_rewrites_src():
    html = '<img src="cid:logo123">'
    out = resolve_cid_images(html, {"logo123": (b"\x89PNG...", "image/png")})
    assert "cid:" not in out
    assert out.startswith('<img src="data:image/png;base64,')


def test_resolve_cid_images_leaves_unknown_cid_untouched():
    html = '<img src="cid:missing">'
    out = resolve_cid_images(html, {"other": (b"data", "image/png")})
    assert out == html


def test_resolve_cid_images_handles_background_attr_and_multiple_refs():
    html = (
        '<td background="cid:bg"><img src="cid:a"><img src="cid:b"></td>'
    )
    cid_map = {
        "bg": (b"1", "image/png"),
        "a": (b"2", "image/jpeg"),
        "b": (b"3", "image/gif"),
    }
    out = resolve_cid_images(html, cid_map)
    assert "cid:" not in out
    assert "data:image/jpeg;base64," in out
    assert "data:image/gif;base64," in out


def test_resolve_cid_images_noop_without_map():
    html = '<img src="cid:x">'
    assert resolve_cid_images(html, {}) == html


def test_extract_bodies_resolves_inline_cid_image_end_to_end():
    outer = MIMEMultipart("related")
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("plain version", "plain"))
    alt.attach(MIMEText(
        '<html><body><img src="cid:logo@abc"></body></html>', "html"
    ))
    outer.attach(alt)
    image = MIMEImage(b"\x89PNG\r\n\x1a\n" + b"0" * 16, "png")
    image.add_header("Content-ID", "<logo@abc>")
    image.add_header("Content-Disposition", "inline", filename="logo.png")
    outer.attach(image)
    outer["From"] = "sender@example.com"
    outer["To"] = "me@example.com"
    outer["Subject"] = "Inline image"

    parsed = parse_rfc822(outer.as_bytes(), account_id=1, folder="inbox", uid="1")
    assert "cid:logo@abc" not in parsed["body_html"]
    assert "data:image/png;base64," in parsed["body_html"]

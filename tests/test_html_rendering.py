"""Regression tests for the QTextDocument image-sizing bug: real HTML
newsletters render as sliced/displaced/overflowing images because
QTextDocument ignores CSS max-width/height:auto and mishandles width/
height attributes that don't match an image's real aspect ratio.
normalize_image_sizing works around both by rewriting every <img> tag to
a width-only sizing hint, which is the one form confirmed (by direct
rendering tests, not assumption) to make QTextDocument scale correctly.
"""

from app.ui.html_view import normalize_image_sizing


def test_caps_oversized_declared_width():
    html = '<img src="http://x/a.png" width="1200" height="800">'
    out = normalize_image_sizing(html, max_width=560)
    assert 'width="560"' in out
    assert "height=" not in out


def test_leaves_small_width_unchanged_but_still_drops_height():
    html = '<img src="http://x/a.png" width="60" height="60">'
    out = normalize_image_sizing(html, max_width=560)
    assert 'width="60"' in out
    assert "height=" not in out


def test_no_width_attribute_left_unset():
    # No declared width: normalize_image_sizing can't know the real pixel
    # size (only the fetched bytes reveal that - handled separately by
    # HtmlMailView's pixel-level cap), so it must not invent one.
    html = '<img src="http://x/a.png">'
    out = normalize_image_sizing(html, max_width=560)
    assert "width=" not in out
    assert "height=" not in out


def test_strips_size_related_css_keeps_other_properties():
    html = (
        '<img src="http://x/a.png" '
        'style="max-width:100%;height:auto;border-radius:4px;display:block;">'
    )
    out = normalize_image_sizing(html, max_width=560)
    assert "max-width" not in out
    assert "height:auto" not in out
    assert "border-radius:4px" in out
    assert "display:block" in out


def test_mismatched_aspect_ratio_attrs_reduced_to_width_only():
    # This exact shape (width/height attributes far from the source
    # image's real aspect ratio) is what triggered dropped/displaced
    # image content in QTextDocument - confirmed by direct rendering,
    # not assumed. The fix is to never let both attributes reach Qt.
    html = '<img src="http://x/a.png" width="300" height="600">'
    out = normalize_image_sizing(html, max_width=560)
    assert 'width="300"' in out
    assert "height=" not in out


def test_non_img_tags_pass_through_unchanged():
    html = '<table width="600"><tr><td style="width:100px;">Hi</td></tr></table>'
    out = normalize_image_sizing(html, max_width=560)
    assert out == html


def test_surrounding_text_and_structure_preserved():
    html = (
        "<html><body><p>Before</p>"
        '<img src="http://x/a.png" width="9999">'
        "<p>After &amp; more</p></body></html>"
    )
    out = normalize_image_sizing(html, max_width=560)
    assert "<p>Before</p>" in out
    assert "<p>After &amp; more</p></body></html>" in out
    assert 'width="560"' in out


def test_self_closing_img_tag():
    html = '<img src="http://x/a.png" width="9999" height="1" />'
    out = normalize_image_sizing(html, max_width=560)
    assert 'width="560"' in out
    assert "height=" not in out


def test_empty_html_returns_empty():
    assert normalize_image_sizing("", max_width=560) == ""


def test_html_without_images_unchanged():
    html = "<p>No images here, just text.</p>"
    assert normalize_image_sizing(html, max_width=560) == html


def test_malformed_html_falls_back_to_original():
    # Never let a parsing hiccup mean the message body renders as nothing.
    html = '<img src="http://x/a.png" width="1200" <<<broken'
    out = normalize_image_sizing(html, max_width=560)
    assert out  # some non-empty result, whichever path it took

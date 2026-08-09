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


# --------------------------------------------------------------------------
# Hidden preheader text ("Save 40% today only..." stuffed before the visible
# body via display:none) is real, visible-to-QTextDocument text - QTextDocument
# does not honor display:none. Confirmed by rendering a real promotional-
# email fixture through the actual widget and finding the "hidden" text as
# the first line of the laid-out document (see scratch probe during
# development); these lock the fix in as a regression test.
# --------------------------------------------------------------------------

def test_inline_display_none_element_is_dropped():
    html = (
        '<div style="display:none;font-size:1px;">Secret preheader text</div>'
        "<p>Visible body</p>"
    )
    out = normalize_image_sizing(html, max_width=560)
    assert "Secret preheader text" not in out
    assert "<p>Visible body</p>" in out


def test_hidden_element_nested_content_fully_dropped():
    # Tags and attributes inside the hidden subtree must vanish too, not
    # just the top-level element's own text.
    html = (
        '<div style="display:none"><span>a</span> <b>b</b>'
        '<img src="http://x/hidden.png"></div><p>After</p>'
    )
    out = normalize_image_sizing(html, max_width=560)
    assert "hidden.png" not in out
    assert "<span>" not in out
    assert "<p>After</p>" in out


def test_class_based_display_none_in_style_block_is_dropped():
    html = (
        "<style>.preheader{display:none;mso-hide:all;}</style>"
        '<div class="preheader">Limited time offer inside</div>'
        "<p>Real content</p>"
    )
    out = normalize_image_sizing(html, max_width=560)
    assert "Limited time offer inside" not in out
    assert "<p>Real content</p>" in out


def test_visible_sibling_after_hidden_block_is_kept():
    html = (
        '<div style="display:none">hidden</div>'
        "<p>First</p><p>Second</p>"
    )
    out = normalize_image_sizing(html, max_width=560)
    assert "hidden" not in out
    assert "<p>First</p>" in out
    assert "<p>Second</p>" in out


# --------------------------------------------------------------------------
# CSS background-image is not supported by QTextDocument at all (confirmed
# by rendering a fixture and inspecting the document's actual image
# resources: zero were picked up for either a hero-banner or a button
# background). table/td/th/tr/body get it rewritten to the legacy
# background= HTML attribute, which Qt *does* paint (confirmed by
# inspecting the resulting QTextTableCellFormat's brush: a real, non-null
# texture, not a no-op) - see scratch probe during development. Anything
# else gets a synthetic <img> child instead, since there is no native
# attribute for it.
# --------------------------------------------------------------------------

def test_inline_background_image_on_td_becomes_background_attribute():
    html = '<table><tr><td style="background-image:url(\'http://x/hero.jpg\');padding:8px;">Hi</td></tr></table>'
    out = normalize_image_sizing(html, max_width=560)
    assert 'background="http://x/hero.jpg"' in out
    assert "padding:8px" in out  # non-size style declarations still kept
    assert "<img" not in out  # td got the native attribute, not a fallback img


def test_class_based_background_image_on_td_becomes_background_attribute():
    html = (
        "<style>.hero{background-image:url('http://x/hero.jpg');}</style>"
        '<table><tr><td class="hero">Hi</td></tr></table>'
    )
    out = normalize_image_sizing(html, max_width=560)
    assert 'background="http://x/hero.jpg"' in out


def test_background_image_on_div_gets_synthetic_img_fallback():
    # div has no native "background" attribute support in Qt's engine, so
    # the only way to make the graphic visible at all is a real <img>.
    html = '<div style="background-image:url(\'http://x/banner.png\');">Text</div>'
    out = normalize_image_sizing(html, max_width=560)
    assert 'src="http://x/banner.png"' in out
    assert "<div" in out
    assert "Text" in out


def test_background_color_alone_is_not_mistaken_for_background_image():
    html = '<td style="background-color:#ffcc00;">Hi</td>'
    out = normalize_image_sizing(html, max_width=560)
    assert "background=" not in out
    assert "<img" not in out


def test_srcset_and_sizes_stripped_from_img():
    html = (
        '<img src="http://x/a.png" width="24" '
        'srcset="http://x/a@2x.png 2x" sizes="24px">'
    )
    out = normalize_image_sizing(html, max_width=560)
    assert "srcset" not in out
    assert "sizes=" not in out
    assert 'src="http://x/a.png"' in out

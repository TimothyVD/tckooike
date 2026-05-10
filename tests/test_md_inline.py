from site_builder import _md_inline


def test_plain_text():
    assert _md_inline("hello") == "hello"


def test_bold():
    assert _md_inline("**word**") == "<strong>word</strong>"


def test_bold_mid_sentence():
    result = _md_inline("text **bold** more")
    assert "<strong>bold</strong>" in result
    assert "text" in result
    assert "more" in result


def test_external_link():
    result = _md_inline("[label](https://example.com)")
    assert 'target="_blank"' in result
    assert 'href="https://example.com"' in result
    assert ">label<" in result


def test_mailto_link_no_target_blank():
    result = _md_inline("[email](mailto:a@b.com)")
    assert 'target="_blank"' not in result
    assert 'href="mailto:a@b.com"' in result


def test_tel_link_no_target_blank():
    result = _md_inline("[phone](tel:+3212345678)")
    assert 'target="_blank"' not in result
    assert 'href="tel:+3212345678"' in result


def test_bold_and_link_combined():
    result = _md_inline("**bold** and [link](https://x.com)")
    assert "<strong>bold</strong>" in result
    assert 'href="https://x.com"' in result


def test_emoji_passthrough():
    assert "🎾" in _md_inline("🎾 text")


def test_empty_string():
    assert _md_inline("") == ""

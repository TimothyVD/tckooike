from site_builder import _md_to_html


def test_heading_h2():
    result = _md_to_html("## Titel")
    assert "font-weight:700" in result
    assert "color:var(--clay-dark)" in result
    assert "Titel" in result


def test_heading_h3():
    result = _md_to_html("### Subtitel")
    assert "font-size:.9rem" in result
    assert "color:var(--clay-dark)" in result
    assert "Subtitel" in result


def test_faq_single_item():
    result = _md_to_html("? Vraag\nAntwoord")
    assert '<ul class="faq-list">' in result
    assert "<strong>" in result
    assert "Vraag" in result
    assert "Antwoord" in result


def test_faq_multiple_items_single_ul():
    # Consecutive FAQ blocks collapse into one <ul>
    result = _md_to_html("? Vraag 1\nAntwoord 1\n\n? Vraag 2\nAntwoord 2")
    assert result.count('<ul class="faq-list">') == 1
    assert result.count("<li>") == 2


def test_bullet_list():
    result = _md_to_html("- item1\n- item2")
    assert "<ul" in result
    assert result.count("<li>") == 2
    assert "item1" in result
    assert "item2" in result


def test_table():
    result = _md_to_html("| A | B |\n|---|---|\n| 1 | 2 |")
    assert '<table class="school-tbl">' in result
    assert "<thead>" in result
    assert "<tbody>" in result
    assert "<th>" in result
    assert "<td>" in result


def test_blockquote():
    result = _md_to_html("> hulptekst")
    assert 'class="help"' in result
    assert "hulptekst" in result


def test_cta_button():
    result = _md_to_html("[cta: Inschrijven](https://example.com)")
    assert 'class="cta-btn"' in result
    assert 'href="https://example.com"' in result
    assert "Inschrijven" in result


def test_cta_multiple_buttons_single_div():
    result = _md_to_html("[cta: A](https://a.com)\n[cta: B](https://b.com)")
    assert result.count('class="cta-btn"') == 2
    assert result.count("<div") == 1


def test_paragraph_first():
    result = _md_to_html("gewone tekst")
    assert result.startswith("<p")
    assert "margin-bottom:14px" in result
    assert "gewone tekst" in result


def test_paragraph_subsequent_has_margin_top():
    result = _md_to_html("eerste\n\ntweede")
    assert "margin-top:6px" in result


def test_intro_style():
    result = _md_to_html("tekst", intro_style=True)
    assert "font-size:.8rem" in result
    assert "var(--text-muted)" in result


def test_br_lines():
    result = _md_to_html("lijn 1\nlijn 2", br_lines=True)
    assert "<br>" in result
    assert "lijn 1" in result
    assert "lijn 2" in result


def test_para_style():
    result = _md_to_html("tekst", para_style="font-size:1rem;")
    assert "font-size:1rem;" in result


def test_empty_input():
    assert _md_to_html("") == ""

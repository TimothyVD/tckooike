"""
Content validation tests for input/*.md files.

These tests catch formatting mistakes that would cause the site to silently
render incorrectly — missing required fields, malformed dates, wrong image
paths, etc. They run against the actual input files on every CI build.
"""
import re
from pathlib import Path

import site_builder

REPO = Path(__file__).parent.parent
INPUT = REPO / "input"

_DATE_RE    = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_DATUM_RE   = re.compile(r'^\d{1,2}/\d{1,2}/\d{4}')  # DD/MM/YYYY [HH:MM]
_URL_RE     = re.compile(r'^https?://')


# ── kalender ──────────────────────────────────────────────────────────────────

def test_kalender_all_events_have_date():
    for ev in site_builder.load_kalender_events(str(INPUT / "kalender.md")):
        assert ev["date"], f"Event has empty date: {ev}"

def test_kalender_hide_after_format():
    for ev in site_builder.load_kalender_events(str(INPUT / "kalender.md")):
        if ev["hideAfter"] is not None:
            assert _DATE_RE.match(ev["hideAfter"]), (
                f"hide-after must be YYYY-MM-DD, got: {ev['hideAfter']!r}"
            )


# ── sponsors ──────────────────────────────────────────────────────────────────

def test_sponsors_all_have_name_and_img():
    for s in site_builder.load_sponsors(str(INPUT / "sponsors.md")):
        assert s["name"], f"Sponsor has empty name: {s}"
        assert s["img"],  f"Sponsor has empty img: {s}"

def test_sponsors_img_path():
    for s in site_builder.load_sponsors(str(INPUT / "sponsors.md")):
        assert s["img"].startswith("images/sponsors/"), (
            f"Sponsor img should start with images/sponsors/, got: {s['img']!r}"
        )

def test_sponsors_url_format():
    for s in site_builder.load_sponsors(str(INPUT / "sponsors.md")):
        if s["url"] is not None:
            assert _URL_RE.match(s["url"]), (
                f"Sponsor URL should start with http(s)://, got: {s['url']!r}"
            )


# ── bestuur ───────────────────────────────────────────────────────────────────

def test_bestuur_all_have_name_and_role():
    for m in site_builder.load_bestuur(str(INPUT / "bestuur.md")):
        assert m["name"], f"Board member has empty name: {m}"
        assert m["role"], f"Board member has empty role: {m}"

def test_bestuur_img_path():
    for m in site_builder.load_bestuur(str(INPUT / "bestuur.md")):
        if m["img"] is not None:
            assert m["img"].startswith("images/bestuur/"), (
                f"Board member img should start with images/bestuur/, got: {m['img']!r}"
            )


# ── welkom ────────────────────────────────────────────────────────────────────

def test_welkom_intro_contains_html():
    result = site_builder.load_welkom(str(INPUT / "welkom.md"))
    assert "<p" in result["intro_html"], "welkom intro_html contains no paragraphs"

def test_welkom_reserveren_contains_cta():
    result = site_builder.load_welkom(str(INPUT / "welkom.md"))
    assert "cta-btn" in result["reserveren_html"], (
        "welkom reserveren section contains no CTA buttons — check [cta: ...](url) syntax"
    )


# ── school ────────────────────────────────────────────────────────────────────

def test_school_all_sections_have_html():
    for s in site_builder.load_school(str(INPUT / "school.md")):
        assert s["html"], f"School section {s['heading']!r} has empty html"


# ── contact ───────────────────────────────────────────────────────────────────

def test_contact_all_sections_have_heading_and_html():
    for s in site_builder.load_contact(str(INPUT / "contact.md")):
        assert s["heading"], f"Contact section has empty heading: {s}"
        assert s["html"],    f"Contact section {s['heading']!r} has empty html"

def test_contact_has_email_link():
    sections = site_builder.load_contact(str(INPUT / "contact.md"))
    combined = " ".join(s["html"] for s in sections)
    assert "mailto:" in combined, "contact.md has no mailto: link"

def test_contact_has_phone_link():
    sections = site_builder.load_contact(str(INPUT / "contact.md"))
    combined = " ".join(s["html"] for s in sections)
    assert "tel:" in combined, "contact.md has no tel: link"


# ── sfeer ─────────────────────────────────────────────────────────────────────

def test_sfeer_filenames_not_empty():
    for img in site_builder.load_sfeer(str(INPUT / "sfeer.md")):
        assert img["f"], f"Sfeer entry has empty filename: {img}"

def test_sfeer_filenames_no_extension():
    # The loader expects filenames without .jpg/.png — a common editing mistake
    for img in site_builder.load_sfeer(str(INPUT / "sfeer.md")):
        assert not re.search(r'\.(jpg|jpeg|png|gif|webp)$', img["f"], re.I), (
            f"Sfeer filename should not include extension, got: {img['f']!r}"
        )


# ── interclub ─────────────────────────────────────────────────────────────────

def test_interclub_datum_format():
    for m in site_builder.load_interclub_matches(str(INPUT / "interclub.md")):
        assert _DATUM_RE.match(m["datum"]), (
            f"Interclub datum should be DD/MM/YYYY [HH:MM], got: {m['datum']!r}"
        )

def test_interclub_clubs_not_empty():
    for m in site_builder.load_interclub_matches(str(INPUT / "interclub.md")):
        assert m["ontvangende_club"], f"Interclub match has empty home club: {m}"
        assert m["bezoekende_club"], f"Interclub match has empty away club: {m}"

def test_interclub_type_not_empty():
    for m in site_builder.load_interclub_matches(str(INPUT / "interclub.md")):
        assert m["type"], f"Interclub match has empty type: {m}"

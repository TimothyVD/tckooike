from pathlib import Path

import site_builder

REPO = Path(__file__).parent.parent
INPUT = REPO / "input"


def test_load_kalender_events():
    events = site_builder.load_kalender_events(str(INPUT / "kalender.md"))
    assert isinstance(events, list)
    assert len(events) > 0
    first = events[0]
    assert set(first.keys()) == {"date", "desc", "note", "hideAfter"}
    assert isinstance(first["date"], str) and first["date"]
    assert isinstance(first["desc"], str)
    # note and hideAfter are str or None
    assert first["note"] is None or isinstance(first["note"], str)
    assert first["hideAfter"] is None or isinstance(first["hideAfter"], str)


def test_load_sponsors():
    sponsors = site_builder.load_sponsors(str(INPUT / "sponsors.md"))
    assert isinstance(sponsors, list)
    assert len(sponsors) > 0
    first = sponsors[0]
    assert set(first.keys()) == {"name", "img", "url"}
    assert isinstance(first["name"], str) and first["name"]
    assert isinstance(first["img"], str) and first["img"]
    assert first["url"] is None or isinstance(first["url"], str)


def test_load_bestuur():
    members = site_builder.load_bestuur(str(INPUT / "bestuur.md"))
    assert isinstance(members, list)
    assert len(members) > 0
    first = members[0]
    assert set(first.keys()) == {"name", "role", "img"}
    assert isinstance(first["name"], str) and first["name"]
    assert isinstance(first["role"], str) and first["role"]
    assert first["img"] is None or isinstance(first["img"], str)


def test_load_welkom():
    result = site_builder.load_welkom(str(INPUT / "welkom.md"))
    assert isinstance(result, dict)
    assert set(result.keys()) == {"intro_html", "reserveren_html"}
    assert isinstance(result["intro_html"], str) and result["intro_html"]
    assert isinstance(result["reserveren_html"], str)


def test_load_school():
    sections = site_builder.load_school(str(INPUT / "school.md"))
    assert isinstance(sections, list)
    assert len(sections) > 0
    first = sections[0]
    assert set(first.keys()) == {"heading", "html"}
    assert isinstance(first["html"], str)


def test_load_ladder():
    result = site_builder.load_ladder(str(INPUT / "ladder.md"))
    assert isinstance(result, str)
    assert result
    assert "faq-list" in result


def test_load_contact():
    sections = site_builder.load_contact(str(INPUT / "contact.md"))
    assert isinstance(sections, list)
    assert len(sections) >= 2
    first = sections[0]
    assert set(first.keys()) == {"heading", "html"}
    assert isinstance(first["heading"], str) and first["heading"]
    assert isinstance(first["html"], str)


def test_load_sfeer():
    images = site_builder.load_sfeer(str(INPUT / "sfeer.md"))
    assert isinstance(images, list)
    assert len(images) > 0
    first = images[0]
    assert set(first.keys()) == {"f", "c", "pos"}
    assert isinstance(first["f"], str) and first["f"]
    # First image in a section carries the caption
    assert isinstance(first["c"], str) and first["c"]
    assert first["pos"] is None or isinstance(first["pos"], str)


def test_load_interclub_matches():
    matches = site_builder.load_interclub_matches(str(INPUT / "interclub.md"))
    assert isinstance(matches, list)
    assert len(matches) > 0
    first = matches[0]
    assert set(first.keys()) == {
        "datum", "reeks", "kapitein", "ontvangende_club", "bezoekende_club", "type"
    }
    for key in ("datum", "reeks", "kapitein", "ontvangende_club", "bezoekende_club", "type"):
        assert isinstance(first[key], str)


def test_load_reglement():
    result = site_builder.load_reglement(str(INPUT / "reglement.md"))
    assert isinstance(result, str)
    assert result
    assert "<p" in result

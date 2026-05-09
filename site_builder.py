from __future__ import annotations

import json
import re
from datetime import date as _date
from pathlib import Path

def _md_inline(text: str) -> str:
    """Convert inline Markdown (bold, links) to HTML."""
    def _link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        target = '' if url.startswith(('mailto:', 'tel:')) else ' target="_blank"'
        return f'<a href="{url}"{target}>{label}</a>'
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _link, text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    return text


def _md_to_html(text: str, *, intro_style: bool = False, br_lines: bool = False, para_style: str = '') -> str:
    """Convert a subset of Markdown to HTML.

    Block-level:
      ## Heading      — bold coloured heading
      ### Subheading  — smaller bold heading
      ? Question      — FAQ item (answer on following lines of same block)
      - item          — <ul> bullet list
      | A | B | C |  — <table class="school-tbl">
      [cta: text](u) — <a class="cta-btn"> button(s)
      paragraph       — <p>

    Inline: **bold**, [text](url / mailto: / tel:)

    intro_style: first paragraph gets muted small style (used by reglement).
    br_lines: lines within a paragraph joined with <br> instead of space (used by contact).
    para_style: extra inline CSS applied to every paragraph (e.g. font-size/line-height).
    """
    blocks = re.split(r'\n{2,}', text.strip())
    out: list[str] = []
    first_para = True
    i = 0

    while i < len(blocks):
        raw = blocks[i].strip()
        if not raw:
            i += 1
            continue
        lines = raw.splitlines()

        if raw.startswith('## '):
            out.append(
                f'<p style="font-weight:700;color:var(--clay-dark);margin:14px 0 4px">'
                f'{_md_inline(raw[3:].strip())}</p>'
            )
            i += 1; continue

        if raw.startswith('### '):
            out.append(
                f'<p style="font-size:.9rem;font-weight:700;margin:14px 0 6px;color:var(--clay-dark)">'
                f'{_md_inline(raw[4:].strip())}</p>'
            )
            i += 1; continue

        # FAQ: block starting with '? ' — first line is question, rest is answer
        if raw.startswith('? '):
            faq_items: list[str] = []
            while i < len(blocks):
                b = blocks[i].strip()
                if not b.startswith('? '):
                    break
                blines = b.splitlines()
                q = _md_inline(blines[0][2:].strip())
                a = _md_inline(' '.join(l.strip() for l in blines[1:])) if len(blines) > 1 else ''
                faq_items.append(f'<li><strong>{q}</strong>{a}</li>')
                i += 1
            out.append('<ul class="faq-list">' + ''.join(faq_items) + '</ul>')
            continue

        # Bullet list
        if all(l.strip().startswith('- ') for l in lines if l.strip()):
            items = ''.join(
                f'<li>{_md_inline(l.strip()[2:])}</li>' for l in lines if l.strip()
            )
            out.append(f'<ul style="margin:8px 0 0 18px;line-height:2">{items}</ul>')
            i += 1; continue

        # Table
        if raw.startswith('|'):
            rows = [
                l for l in lines
                if l.strip().startswith('|') and not re.match(r'^\|[\s\-|]+\|$', l.strip())
            ]
            if rows:
                thead = '<tr>' + ''.join(
                    f'<th>{_md_inline(c.strip())}</th>'
                    for c in rows[0].strip('|').split('|')
                ) + '</tr>'
                tbody = ''.join(
                    '<tr>' + ''.join(
                        f'<td>{_md_inline(c.strip())}</td>'
                        for c in row.strip('|').split('|')
                    ) + '</tr>'
                    for row in rows[1:]
                )
                out.append(
                    f'<div class="tbl-wrap"><table class="school-tbl">'
                    f'<thead>{thead}</thead><tbody>{tbody}</tbody></table></div>'
                )
            i += 1; continue

        # Blockquote: "> text" → muted help paragraph
        if raw.startswith('> '):
            out.append(f'<p class="help" style="margin-top:10px">{_md_inline(raw[2:].strip())}</p>')
            i += 1; continue

        # CTA-only block: every non-empty line is [cta: label](url)
        _cta_re = re.compile(r'^\[cta:([^\]]+)\]\(([^)]+)\)$')
        if all(_cta_re.match(l.strip()) for l in lines if l.strip()):
            buttons = ''.join(
                f'<a class="cta-btn" href="{_cta_re.match(l.strip()).group(2)}" target="_blank">'
                f'{_cta_re.match(l.strip()).group(1).strip()}</a>'
                for l in lines if l.strip()
            )
            out.append(f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:14px">{buttons}</div>')
            i += 1; continue

        # Regular paragraph
        para = (
            '<br>'.join(_md_inline(l.strip()) for l in lines if l.strip())
            if br_lines
            else _md_inline(raw.replace('\n', ' '))
        )
        if intro_style and first_para:
            out.append(f'<p style="font-size:.8rem;color:var(--text-muted);margin-bottom:14px">{para}</p>')
        elif para_style:
            out.append(f'<p style="{para_style}margin-bottom:14px">{para}</p>')
        elif first_para:
            out.append(f'<p style="margin-bottom:14px">{para}</p>')
        else:
            out.append(f'<p style="margin-top:6px">{para}</p>')
        first_para = False
        i += 1

    return ''.join(out)


def load_kalender_events(path: str = "input/kalender.md") -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    events = []
    for block in re.split(r'\n(?=## )', text.strip()):
        lines = block.strip().splitlines()
        if not lines or not lines[0].startswith("## "):
            continue
        header = lines[0][3:]
        if "|" in header:
            date_part, desc_part = header.split("|", 1)
        else:
            date_part, desc_part = header, ""
        date = date_part.strip()
        desc = desc_part.strip()

        body_lines = [l for l in lines[1:] if l.strip()]
        hide_after = None
        note_lines = []
        for line in body_lines:
            m = re.match(r'hide-after:\s*(\S+)', line.strip())
            if m:
                hide_after = m.group(1)
            else:
                note_lines.append(line.strip())

        note_md = " ".join(note_lines).strip() or None
        note_html = _md_inline(note_md) if note_md else None

        events.append({"date": date, "desc": desc, "note": note_html, "hideAfter": hide_after})
    return events


def load_sponsors(path: str = "input/sponsors.md") -> list[dict]:
    """Load sponsors from a Markdown file.

    Format:
      - Naam | images/sponsors/bestand.png | https://url   (url is optional)
    """
    text = Path(path).read_text(encoding="utf-8")
    sponsors = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        parts = [p.strip() for p in line[1:].split("|")]
        if len(parts) < 2:
            continue
        sponsors.append({
            "name": parts[0],
            "img":  parts[1],
            "url":  parts[2] if len(parts) > 2 else None,
        })
    return sponsors


def load_reglement(path: str = "input/reglement.md") -> str:
    text = Path(path).read_text(encoding="utf-8")
    return _md_to_html(text, intro_style=True)


def load_bestuur(path: str = "input/bestuur.md") -> list[dict]:
    """Load board members from a Markdown file.

    Format:
      - Naam | Rol | images/bestuur/foto.jpg   (foto is optional)
    """
    text = Path(path).read_text(encoding="utf-8")
    members = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        parts = [p.strip() for p in line[1:].split("|")]
        if len(parts) < 2:
            continue
        members.append({
            "name": parts[0],
            "role": parts[1],
            "img":  parts[2] if len(parts) > 2 else None,
        })
    return members


def load_welkom(path: str = "input/welkom.md") -> dict:
    text = Path(path).read_text(encoding="utf-8")
    parts = re.split(r'\n(?=## )', text.strip(), maxsplit=1)
    intro_html = _md_to_html(parts[0].strip(), para_style='font-size:1.05rem;line-height:1.8;')
    idx = intro_html.rfind('margin-bottom:14px')
    if idx != -1:
        intro_html = intro_html[:idx] + 'margin-bottom:4px' + intro_html[idx + 18:]
    reserveren_html = ''
    if len(parts) > 1:
        body = '\n'.join(parts[1].strip().splitlines()[1:]).strip()
        reserveren_html = _md_to_html(body, para_style='font-size:.92rem;line-height:1.8;')
    return {"intro_html": intro_html, "reserveren_html": reserveren_html}


def load_school(path: str = "input/school.md") -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    sections: list[dict] = []
    for block in re.split(r'\n(?=## )', text.strip()):
        lines = block.strip().splitlines()
        if not lines:
            continue
        if lines[0].startswith('## '):
            heading = lines[0][3:].strip()
            body = '\n'.join(lines[1:]).strip()
        else:
            heading = None
            body = block.strip()
        sections.append({"heading": heading, "html": _md_to_html(body)})
    return sections


def load_ladder(path: str = "input/ladder.md") -> str:
    text = Path(path).read_text(encoding="utf-8")
    return _md_to_html(text)


def load_contact(path: str = "input/contact.md") -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    sections: list[dict] = []
    for block in re.split(r'\n(?=## )', text.strip()):
        lines = block.strip().splitlines()
        if not lines or not lines[0].startswith('## '):
            continue
        heading = lines[0][3:].strip()
        body = '\n'.join(lines[1:]).strip()
        sections.append({"heading": heading, "html": _md_to_html(body, br_lines=True)})
    return sections


def load_sfeer(path: str = "input/sfeer.md") -> list[dict]:
    """Load sfeer images from a Markdown file.

    Format:
      ## Section caption
      - filename            (object-position defaults to unset)
      - filename | center 65%
    """
    text = Path(path).read_text(encoding="utf-8")
    images: list[dict] = []
    for block in re.split(r'\n(?=## )', text.strip()):
        lines = block.strip().splitlines()
        if not lines:
            continue
        caption = lines[0][3:].strip() if lines[0].startswith('## ') else ''
        first = True
        for line in lines[1:] if lines[0].startswith('## ') else lines:
            line = line.strip()
            if not line.startswith('- '):
                continue
            parts = [p.strip() for p in line[2:].split('|')]
            images.append({
                "f":   parts[0],
                "c":   caption if first else '',
                "pos": parts[1] if len(parts) > 1 else None,
            })
            first = False
    return images


def load_interclub_matches(path: str = "input/interclub.md") -> list[dict]:
    """Load interclub matches from a Markdown file.

    Format:
      ## TYPE | Kapitein | Reeks      (Reeks is optional)
      - DD/MM/YYYY HH:MM | Home Club | Away Club
    """
    text = Path(path).read_text(encoding="utf-8")
    rows: list[dict] = []
    for block in re.split(r'\n(?=## )', text.strip()):
        lines = block.strip().splitlines()
        if not lines or not lines[0].startswith("## "):
            continue
        header = [p.strip() for p in lines[0][3:].split("|")]
        type_   = header[0] if len(header) > 0 else ""
        kapitein = header[1] if len(header) > 1 else ""
        reeks    = header[2] if len(header) > 2 else ""
        for line in lines[1:]:
            line = line.strip()
            if not line.startswith("-"):
                continue
            parts = [p.strip() for p in line[1:].split("|")]
            if len(parts) < 3:
                continue
            rows.append({
                "datum":           parts[0],
                "reeks":           reeks,
                "kapitein":        kapitein,
                "ontvangende_club": parts[1],
                "bezoekende_club": parts[2],
                "type":            type_,
            })
    return rows

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TC Kooike</title>
  <link rel="icon" type="image/png" href="images/logo.png">
  <meta property="og:title" content="TC Kooike">
  <meta property="og:description" content="Welkom bij TC Kooike — jouw tennisclub in de regio.">
  <meta property="og:image" content="images/logo.png">
  <meta property="og:type" content="website">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --clay: #C1440E; --clay-dark: #8B2500; --clay-light: #E8896A;
      --clay-bg: #FBE9E7; --bg: #F9F5F3; --card: #FFFFFF;
      --border: #DDD0CA; --text: #2C1810; --text-muted: #7D5A50;
      --win: #2E7D32; --win-bg: #E8F5E9;
      --loss: #C62828; --loss-bg: #FFEBEE;
      --draw-color: #E65100; --draw-bg: #FFF3E0;
    }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); }
    a { color: var(--clay); text-decoration: none; }
    /* ── Header ── */
    .site-header {
      background: var(--clay); color: #fff;
      padding: 0 24px; height: 92px;
      display: flex; align-items: center; gap: 14px;
      box-shadow: 0 2px 8px rgba(0,0,0,.25);
      position: sticky; top: 0; z-index: 100;
    }
    .hdr-logo { font-size: 2rem; line-height: 1; flex-shrink: 0; }
    .hdr-text { flex: 1; min-width: 0; }
    .hdr-text h1 { font-size: 1.3rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .hdr-text .sub { font-size: .82rem; opacity: .85; margin-top: 2px; }
    .hdr-actions { display: flex; gap: 8px; flex-shrink: 0; }
    .btn {
      display: inline-flex; align-items: center; gap: 5px;
      padding: 7px 13px; border-radius: 6px; border: none;
      cursor: pointer; font-size: .84rem; font-weight: 600;
      transition: background .15s;
    }
    .btn-ghost { background: rgba(255,255,255,.15); color: #fff; }
    .btn-ghost:hover { background: rgba(255,255,255,.3); }
    .btn-icon { padding: 6px 10px; display:flex; align-items:center; justify-content:center; }
    .btn-icon svg { display:block; }
    /* ── Tab nav ── */
    .tab-nav {
      position: sticky; top: 92px; z-index: 90;
      background: var(--card); border-bottom: 2px solid var(--border);
      padding: 0 24px; display: flex; gap: 2px; align-items: stretch;
      overflow-x: auto; scrollbar-width: none;
    }
    .nav-spacer { flex: 1; }
    .nav-padel-link {
      display: flex; align-items: center; gap: 7px;
      padding: 10px 16px; font-size: .88rem; font-weight: 600;
      color: var(--clay-dark); text-decoration: none; white-space: nowrap;
      border-bottom: 3px solid transparent;
      border-left: 1px solid var(--border); margin-left: 4px;
      transition: color .15s, background .15s;
    }
    .nav-padel-link:hover { color: var(--clay); background: var(--clay-bg); }
    .tab-nav::-webkit-scrollbar { display: none; }
    .tab-btn {
      padding: 10px 18px; border: none; background: none;
      cursor: pointer; font-size: .88rem; font-weight: 500;
      color: var(--text-muted); border-bottom: 3px solid transparent;
      white-space: nowrap; transition: color .15s, border-color .15s;
    }
    .tab-btn:hover { color: var(--clay); }
    .tab-btn.active { color: var(--clay); border-bottom-color: var(--clay); font-weight: 700; }
    /* ── Content ── */
    .main { max-width: 1100px; margin: 0 auto; padding: 24px 20px; }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    /* ── Card ── */
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 18px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.07); }
    .card-head {
      background: var(--clay); color: #fff;
      padding: 11px 18px; font-weight: 700; font-size: .95rem;
      display: flex; align-items: center; justify-content: space-between;
    }
    .card-head.collapsible { cursor: pointer; user-select: none; }
    .toggle-icon { transition: transform .2s; }
    .card-head.collapsed .toggle-icon { transform: rotate(-90deg); }
    .card-body { padding: 16px 18px; }
    .card-body.hidden { display: none; }
    /* ── Tables ── */
    .tbl-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: .88rem; }
    thead th { background: var(--clay); color: #fff; padding: 9px 12px; text-align: left; font-weight: 600; white-space: nowrap; }
    thead th select.th-filter { background: transparent; color: #fff; border: none; font: inherit; font-weight: 600; cursor: pointer; outline: none; padding: 0; margin: 0; width: 100%; appearance: none; -webkit-appearance: none; }
    thead th select.th-filter option { background: var(--clay-dark); color: #fff; }
    thead th.th-active-filter { background: var(--clay-dark); }
    tbody tr:nth-child(even):not(.date-row) { background: var(--clay-bg); }
    tbody tr:hover:not(.date-row) { background: #eeddd7; }
    td { padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }
    .date-row td { background: #F2E0D9 !important; color: var(--clay-dark); font-weight: 700; padding: 5px 12px !important; font-size: .8rem; letter-spacing: .03em; }
    /* ── Score inputs ── */
    .score-wrap { display: flex; align-items: center; gap: 5px; }
    .score-in {
      width: 44px; height: 30px;
      border: 1.5px solid var(--border); border-radius: 5px;
      text-align: center; font-size: .95rem; font-weight: 600;
      background: #fff; transition: border-color .15s;
    }
    .score-in:focus { outline: none; border-color: var(--clay); box-shadow: 0 0 0 2px var(--clay-bg); }
    .score-sep { font-weight: 700; color: var(--text-muted); }
    /* Win highlighting on table rows */
    tr.winner-a .score-in[data-side="a"] { color: var(--win); border-color: var(--win); }
    tr.winner-a .score-in[data-side="b"] { color: var(--text-muted); }
    tr.winner-b .score-in[data-side="b"] { color: var(--win); border-color: var(--win); }
    tr.winner-b .score-in[data-side="a"] { color: var(--text-muted); }
    /* ── Badges ── */
    .badge { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: .78rem; font-weight: 700; }
    .badge-w { background: var(--win-bg); color: var(--win); }
    .badge-l { background: var(--loss-bg); color: var(--loss); }
    .badge-d { background: var(--draw-bg); color: var(--draw-color); }
    .badge-n { background: #f0f0f0; color: #bbb; font-weight: 400; }
    /* ── Standings ── */
    .s-wrap thead th { text-align: center; }
    .s-wrap thead th:first-child, .s-wrap thead th:nth-child(2) { text-align: left; }
    .s-wrap td { text-align: center; }
    .s-wrap td:first-child, .s-wrap td:nth-child(2) { text-align: left; }
    .s-rank { font-weight: 600; color: var(--text-muted); }
    .s-name { font-weight: 600; }
    .s-pts { font-weight: 700; color: var(--clay-dark); }
    .s-empty { color: var(--text-muted); font-style: italic; padding: 18px 0; text-align: center; }
    /* ── Teams grid ── */
    .teams-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
    .team-card { border: 1px solid var(--border); border-radius: 8px; padding: 13px 15px; }
    .tc-name { font-weight: 700; color: var(--clay-dark); margin-bottom: 6px; }
    .tc-detail { font-size: .82rem; color: var(--text-muted); line-height: 1.8; }
    /* ── Info chips ── */
    .chips { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
    .chip { background: var(--clay-bg); border: 1px solid var(--clay-light); border-radius: 20px; padding: 4px 13px; font-size: .82rem; color: var(--clay-dark); font-weight: 500; }
    /* ── Toast ── */
    .toast {
      position: fixed; bottom: 20px; right: 20px; z-index: 999;
      background: #323232; color: #fff;
      padding: 11px 18px; border-radius: 8px; font-size: .88rem; font-weight: 500;
      box-shadow: 0 4px 14px rgba(0,0,0,.3);
      opacity: 0; transition: opacity .3s; pointer-events: none;
    }
    .toast.show { opacity: 1; }
    /* ── Help text ── */
    .help { font-size: .8rem; color: var(--text-muted); margin-top: 8px; }
    /* ── Nav separator & group labels ── */
    .tab-nav { align-items: center; }
    .tab-sep { width: 1px; height: 26px; background: var(--border); margin: 0 6px; flex-shrink: 0; }
    /* ── Static info sections ── */
    .info-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
    @media (max-width: 600px) { .info-grid { grid-template-columns: 1fr; } }
    .info-card { border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; background: var(--card); }
    .info-card h3 { color: var(--clay-dark); font-size: .95rem; margin-bottom: 8px; }
    .info-card p, .info-card li { font-size: .85rem; color: var(--text-muted); line-height: 1.7; }
    .kal-grid { display: flex; flex-direction: column; gap: 8px; }
    .kal-item { display: flex; gap: 14px; align-items: flex-start; padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--card); }
    .kal-date { min-width: 145px; font-size: .82rem; font-weight: 700; color: var(--clay-dark); padding-top: 2px; }
    .kal-desc { font-size: .88rem; color: var(--text); flex: 1; }
    .kal-desc small { display: block; color: var(--text-muted); font-size: .78rem; margin-top: 2px; }
    .sponsor-grid { display: flex; flex-wrap: wrap; gap: 10px; }
    .sponsor-pill { padding: 8px 16px; border: 1.5px solid var(--clay-light); border-radius: 24px; font-size: .85rem; font-weight: 500; color: var(--clay-dark); text-decoration: none; background: var(--clay-bg); transition: background .15s, color .15s; }
    .sponsor-pill:hover { background: var(--clay); color: #fff; }
    .contact-block { font-size: .9rem; line-height: 2; }
    .contact-block a { color: var(--clay); }
    table.school-tbl { font-size: .85rem; }
    table.school-tbl td { padding: 7px 11px; }
    table.school-tbl td:last-child { font-weight: 700; color: var(--clay-dark); text-align: right; white-space: nowrap; }
    .faq-list { list-style: none; padding: 0; display: flex; flex-direction: column; gap: 10px; }
    .faq-list li { padding: 11px 14px; background: var(--clay-bg); border-radius: 8px; font-size: .86rem; line-height: 1.6; }
    .faq-list li strong { color: var(--clay-dark); display: block; margin-bottom: 3px; font-size: .88rem; }
    .cta-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--clay); color: #fff !important; padding: 10px 20px; border-radius: 7px; font-size: .9rem; font-weight: 600; margin-top: 16px; text-decoration: none; transition: background .15s; }
    .cta-btn:hover { background: var(--clay-dark); }
    /* ── Images ── */
    .hero-img { width: 100%; max-height: 280px; object-fit: cover; border-radius: 10px; margin-bottom: 16px; display: block; }
    .hero-img-sm { width: 100%; max-height: 180px; object-fit: cover; border-radius: 8px; margin-bottom: 12px; display: block; }
    .board-photo { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 3px solid var(--clay-light); flex-shrink: 0; }
    .board-initials { display: flex; align-items: center; justify-content: center; background: var(--clay); color: #fff; font-weight: 700; font-size: 1.2rem; letter-spacing: .03em; }
    .board-card { display: flex; align-items: center; gap: 14px; border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; background: var(--card); }
    .board-info { flex: 1; min-width: 0; }
    .board-name { font-weight: 700; color: var(--clay-dark); margin-bottom: 3px; }
    .board-role { font-size: .82rem; color: var(--text-muted); line-height: 1.5; }
    .board-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
    .photo-gallery { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }
    .photo-gallery a.lb-trigger { display: block; cursor: zoom-in; }
    .photo-gallery img { width: 100%; height: 240px; object-fit: cover; object-position: center top; border-radius: 7px; transition: opacity .15s; }
    .photo-gallery a.lb-trigger:hover img { opacity: .88; }
    /* ── Lightbox ── */
    #lb-overlay { display:none; position:fixed; inset:0; z-index:9999; background:rgba(0,0,0,.88); align-items:center; justify-content:center; }
    #lb-overlay.open { display:flex; }
    #lb-overlay img { max-width:92vw; max-height:92vh; border-radius:6px; box-shadow:0 4px 32px rgba(0,0,0,.6); }
    #lb-close { position:absolute; top:18px; right:24px; font-size:2rem; color:#fff; cursor:pointer; line-height:1; background:none; border:none; opacity:.8; }
    #lb-close:hover { opacity:1; }
    /* .sponsor-logo-grid overridden below by 3-per-row grid rule */
    .sponsor-logo-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 16px; }
    .sponsor-logo-grid a { display: flex; align-items: center; justify-content: center; padding: 0; border: 1px solid var(--border); border-radius: 8px; background: #fff; transition: box-shadow .15s; height: 160px; box-sizing: border-box; overflow: hidden; }
    .sponsor-logo-grid a:hover { box-shadow: 0 0 0 2px var(--clay-light); }
    .sponsor-logo-grid img { width: 100%; height: 100%; object-fit: contain; display: block; }
    @media (max-width: 480px) { .sponsor-logo-grid { grid-template-columns: repeat(2, 1fr); } }
    @keyframes marquee { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
    .marquee-wrap { overflow: hidden; width: 100%; flex: 1; display: flex; min-height: 80px; }
    .marquee-track { display: flex; align-items: center; gap: 24px; width: max-content; animation: marquee 50s linear infinite; height: 100%; }
    .marquee-track:hover { animation-play-state: paused; }
    .marquee-track img { height: 100%; min-height: 70px; max-height: 200px; width: auto; max-width: 150px; object-fit: contain; flex-shrink: 0; filter: grayscale(20%); transition: filter .2s; }
    .marquee-track img:hover { filter: none; }
    .ladder-img { width: 100%; max-width: 340px; display: block; margin: 0 auto 16px; }
    .whackit-logo { height: 220px; object-fit: contain; margin-bottom: 14px; display: block; }
    /* ── Responsive ── */
    @media (max-width: 640px) {
      .hdr-text h1 { font-size: 1.05rem; }
      .btn-label { display: none; }
      .tab-btn { padding: 10px 11px; font-size: .8rem; }
      .main { padding: 14px 10px; }
      .kal-date { min-width: 100px; }
      .welkom-bottom-grid { grid-template-columns: 1fr !important; }
    }
    @media print {
      .site-header, .tab-nav { display: none !important; }
      .tab-panel { display: block !important; }
      .card { break-inside: avoid; }
    }
  </style>
  <script data-goatcounter="https://tckooike.goatcounter.com/count"
          async src="//gc.zgo.at/count.js"></script>
</head>
<body>

<header class="site-header">
  <img src="images/logo.png" alt="TC Kooike" style="height:80px;width:80px;object-fit:contain;border-radius:50%;background:#fff;padding:3px;flex-shrink:0">
  <div class="hdr-text">
    <h1 id="js-title">TC Kooike</h1>
  </div>
  <div class="hdr-actions">
    <a href="https://www.facebook.com/TennisclubtKooike" target="_blank" class="btn btn-ghost btn-icon" title="TC Kooike op Facebook" aria-label="Facebook">
      <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M22 12c0-5.522-4.478-10-10-10S2 6.478 2 12c0 4.991 3.657 9.128 8.438 9.878v-6.987H7.898V12h2.54V9.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V12h2.773l-.443 2.891h-2.33V21.88C18.343 21.128 22 16.991 22 12z"/></svg>
    </a>
    <a href="https://www.instagram.com/tc_kooike" target="_blank" class="btn btn-ghost btn-icon" title="TC Kooike op Instagram" aria-label="Instagram">
      <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 1.366.062 2.633.336 3.608 1.311.975.975 1.249 2.242 1.311 3.608.058 1.266.07 1.646.07 4.85s-.012 3.584-.07 4.85c-.062 1.366-.336 2.633-1.311 3.608-.975.975-2.242 1.249-3.608 1.311-1.266.058-1.646.07-4.85.07s-3.584-.012-4.85-.07c-1.366-.062-2.633-.336-3.608-1.311-.975-.975-1.249-2.242-1.311-3.608C2.175 15.584 2.163 15.204 2.163 12s.012-3.584.07-4.85c.062-1.366.336-2.633 1.311-3.608.975-.975 2.242-1.249 3.608-1.311C8.416 2.175 8.796 2.163 12 2.163zm0-2.163C8.741 0 8.333.014 7.053.072 5.775.131 4.602.425 3.635 1.392 2.668 2.359 2.374 3.532 2.315 4.81 2.257 6.09 2.243 6.498 2.243 12c0 5.502.014 5.91.072 7.19.059 1.278.353 2.451 1.32 3.418.967.967 2.14 1.261 3.418 1.32C8.333 23.986 8.741 24 12 24s3.667-.014 4.947-.072c1.278-.059 2.451-.353 3.418-1.32.967-.967 1.261-2.14 1.32-3.418.058-1.28.072-1.688.072-7.19 0-5.502-.014-5.91-.072-7.19-.059-1.278-.353-2.451-1.32-3.418C19.398.425 18.225.131 16.947.072 15.667.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zm0 10.162a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z"/></svg>
    </a>
    <a href="https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/lid-worden?clubId=2158" target="_blank" class="btn btn-ghost" title="Lid worden bij TC Kooike">
      <span>🎾</span><span class="btn-label">Lid worden? Schrijf je hier in.</span>
    </a>
    <button class="btn btn-ghost" id="btn-import-trigger" title="Import scores from JSON file" style="display:none">
      <span>📥</span><span class="btn-label">Import</span>
    </button>
    <button class="btn btn-ghost" id="btn-export" title="Export scores to JSON file" style="display:none">
      <span>📤</span><span class="btn-label">Export</span>
    </button>
  </div>
  <input type="file" id="file-import" accept=".json" style="display:none">
</header>

<nav class="tab-nav" id="tab-nav"></nav>
<main class="main" id="main-content"></main>
<div class="toast" id="toast"></div>
<div id="lb-overlay" role="dialog" aria-modal="true">
  <button id="lb-close" aria-label="Sluiten">&times;</button>
  <img id="lb-img" src="" alt="">
</div>

<script>
/* ═══════════════════════════════════════════════════════
   Schedule data — embedded at generation time
   ═══════════════════════════════════════════════════════ */
const DATA = __SCHEDULE_DATA__;

const STORAGE_KEY = ('cs_scores__' + DATA.club_name + '__' + DATA.season)
  .replace(/[^\w]/g, '_');

/* ── State ── */
let scores = {};   // { matchId: { a: number|null, b: number|null } }

/* ═══════════════════════════════════════════════════════
   Toast
   ═══════════════════════════════════════════════════════ */
let _tTimer;
function toastMsg(msg, dur = 2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_tTimer);
  _tTimer = setTimeout(() => el.classList.remove('show'), dur);
}

/* ═══════════════════════════════════════════════════════
   Persistence — localStorage + optional scores.json fetch
   ═══════════════════════════════════════════════════════ */
function loadLocal() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) scores = JSON.parse(raw);
  } catch (_) {}
}
function saveLocal() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(scores)); } catch (_) {}
}
async function fetchServerScores() {
  /* If scores.json is committed next to this HTML in GitHub Pages,
     it is loaded as the baseline; local edits always take precedence. */
  try {
    const r = await fetch('./scores.json', { cache: 'no-cache' });
    if (!r.ok) return;
    const srv = await r.json();
    if (srv && typeof srv === 'object') {
      scores = Object.assign({}, srv, scores);  // local wins on conflict
      saveLocal();
    }
  } catch (_) {}   /* file absent → silent */
}

/* ═══════════════════════════════════════════════════════
   Export / Import
   ═══════════════════════════════════════════════════════ */
function exportScores() {
  const blob = new Blob([JSON.stringify(scores, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'scores.json';
  a.click();
  URL.revokeObjectURL(a.href);
  toastMsg('Exported scores.json — commit it to GitHub Pages to share results!');
}
function importScores(file) {
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const data = JSON.parse(e.target.result);
      Object.assign(scores, data);
      saveLocal();
      refreshAll();
      toastMsg('Imported scores for ' + Object.keys(data).length + ' matches');
    } catch (_) {
      toastMsg('Could not parse file — expected a scores.json');
    }
  };
  reader.readAsText(file);
}

/* ═══════════════════════════════════════════════════════
   Score helpers
   ═══════════════════════════════════════════════════════ */
function getScore(id) { return scores[id] || { a: null, b: null }; }
function setScore(id, side, raw) {
  if (!scores[id]) scores[id] = { a: null, b: null };
  scores[id][side] = (raw === '' || raw == null) ? null : Number(raw);
  saveLocal();
}
function resultForA(id) {
  const s = getScore(id);
  if (s.a === null || s.b === null) return null;
  if (s.a > s.b) return 'w';
  if (s.a < s.b) return 'l';
  return 'd';
}

/* ═══════════════════════════════════════════════════════
   Standings
   ═══════════════════════════════════════════════════════ */
function computeStandings(poule) {
  const ms = DATA.matches.filter(m => m.poule === poule);
  const st = {};
  for (const t of (DATA.teams_by_poule[poule] || [])) {
    st[t.name] = { p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 };
  }
  for (const m of ms) {
    const s = getScore(m.id);
    if (s.a === null || s.b === null) continue;
    if (!st[m.team_a]) st[m.team_a] = { p:0, w:0, d:0, l:0, gf:0, ga:0, pts:0 };
    if (!st[m.team_b]) st[m.team_b] = { p:0, w:0, d:0, l:0, gf:0, ga:0, pts:0 };
    st[m.team_a].p++; st[m.team_b].p++;
    st[m.team_a].gf += s.a; st[m.team_a].ga += s.b;
    st[m.team_b].gf += s.b; st[m.team_b].ga += s.a;
    if (s.a > s.b) {
      st[m.team_a].w++; st[m.team_a].pts += 2; st[m.team_b].l++;
    } else if (s.b > s.a) {
      st[m.team_b].w++; st[m.team_b].pts += 2; st[m.team_a].l++;
    } else {
      st[m.team_a].d++; st[m.team_a].pts++;
      st[m.team_b].d++; st[m.team_b].pts++;
    }
  }
  return Object.entries(st)
    .map(([name, s]) => ({ name, ...s }))
    .sort((a, b) => b.pts - a.pts || b.w - a.w || (b.gf - b.ga) - (a.gf - a.ga));
}

/* ═══════════════════════════════════════════════════════
   HTML helpers
   ═══════════════════════════════════════════════════════ */
function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s == null ? '' : s);
  return d.innerHTML;
}
function fmtDate(ds) {
  try {
    return new Date(ds + 'T00:00:00').toLocaleDateString(undefined,
      { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
  } catch (_) { return ds; }
}
function badgeHtml(res) {
  if (!res) return '<span class="badge badge-n">–</span>';
  if (res === 'w') return '<span class="badge badge-w">W</span>';
  if (res === 'l') return '<span class="badge badge-l">L</span>';
  return '<span class="badge badge-d">D</span>';
}
function rankSymbol(i) { return ['🥇','🥈','🥉'][i] || String(i + 1); }

/* ═══════════════════════════════════════════════════════
   Build UI
   ═══════════════════════════════════════════════════════ */
const SPONSORS = DATA.sponsors || [];
const STATIC_TABS = [
  { id: 'welkom',   label: '🏠 Welkom' },
  { id: 'kalender', label: '📅 Kalender' },
  { id: 'interclub',label: '🎾 Interclub' },
  { id: 'bestuur',  label: '👥 Bestuur' },
  { id: 'sfeer',    label: '📸 Sfeerbeelden' },
  { id: 'school',   label: '🎾 Tennisschool' },
  { id: 'ladder',   label: '🪜 Laddercompetitie' },
  { id: 'sponsors', label: '🤝 Sponsors' },
  { id: 'contact',  label: '📞 Contact' },
];
function buildNav() {
  const nav = document.getElementById('tab-nav');
  let html = STATIC_TABS.map((t, i) =>
    '<button class="tab-btn' + (i === 0 ? ' active' : '') + '" data-tab="' + t.id + '">' + esc(t.label) + '</button>'
  ).join('');
  html += '<div class="nav-spacer"></div>';
  html += '<a href="https://www.padelkooike.be/" target="_blank" class="nav-padel-link" title="Padel Kooike">' +
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="#c8e63c"/><path d="M5.5,7 C10,9.5 10,14.5 5.5,17" stroke="white" stroke-width="2.2" fill="none" stroke-linecap="round"/><path d="M18.5,7 C14,9.5 14,14.5 18.5,17" stroke="white" stroke-width="2.2" fill="none" stroke-linecap="round"/></svg>' +
    ' Padel Kooike</a>';
  nav.innerHTML = html;
  nav.addEventListener('click', e => {
    const btn = e.target.closest('.tab-btn');
    if (!btn) return;
    nav.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    switchTab(btn.dataset.tab);
  });
}
function switchTab(id) {
  const validId = STATIC_TABS.find(t => t.id === id) ? id : STATIC_TABS[0].id;
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  const el = document.getElementById('tp-' + validId);
  if (el) el.classList.add('active');
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === validId)
  );
  if (location.hash !== '#' + validId) history.replaceState(null, '', '#' + validId);
}
function buildAllPanels() {
  const root = document.getElementById('main-content');
  let html = '<div class="tab-panel" id="tp-overview">' + buildOverview() + '</div>';
  for (const p of DATA.poules) {
    html += '<div class="tab-panel" id="tp-p-' + esc(p) + '">' + buildPoule(p) + '</div>';
  }
  for (const t of STATIC_TABS) {
    html += '<div class="tab-panel" id="tp-' + esc(t.id) + '">' + buildStaticPanel(t.id) + '</div>';
  }
  root.innerHTML = html;
  const hashTab = location.hash.slice(1);
  switchTab(hashTab || STATIC_TABS[0].id);
  window.addEventListener('hashchange', () => switchTab(location.hash.slice(1)));
  root.querySelectorAll('.score-in').forEach(inp => inp.addEventListener('change', onScoreChange));
}

/* ── Overview panel ── */
function buildOverview() {
  const multi = DATA.poules.length > 1;
  const sorted = [...DATA.matches].sort((a, b) =>
    a.date !== b.date ? a.date.localeCompare(b.date) :
    a.time !== b.time ? a.time.localeCompare(b.time) :
    String(a.terrain).localeCompare(String(b.terrain))
  );
  let rows = '', last = null;
  for (const m of sorted) {
    if (m.date !== last) {
      last = m.date;
      rows += '<tr class="date-row"><td colspan="' + (multi ? 7 : 6) + '">' + esc(fmtDate(m.date)) + '</td></tr>';
    }
    const s = getScore(m.id);
    const va = s.a !== null ? s.a : '', vb = s.b !== null ? s.b : '';
    const res = resultForA(m.id);
    const tr = res === 'w' ? 'winner-a' : res === 'l' ? 'winner-b' : '';
    const pCell = multi ? '<td>' + esc(m.poule) + '</td>' : '';
    rows += '<tr class="' + tr + '" data-match-row="' + esc(m.id) + '">' +
      pCell +
      '<td>' + esc(m.time) + '</td>' +
      '<td>' + esc(m.terrain) + '</td>' +
      '<td><strong>' + esc(m.team_a) + '</strong></td>' +
      '<td><div class="score-wrap">' +
        '<input class="score-in" type="number" min="0" max="99" data-match="' + esc(m.id) + '" data-side="a" value="' + va + '" placeholder="—">' +
        '<span class="score-sep">–</span>' +
        '<input class="score-in" type="number" min="0" max="99" data-match="' + esc(m.id) + '" data-side="b" value="' + vb + '" placeholder="—">' +
      '</div></td>' +
      '<td><strong>' + esc(m.team_b) + '</strong></td>' +
    '</tr>';
  }
  const pHead = multi ? '<th>Poule</th>' : '';
  const nDone = DATA.matches.filter(m => { const s = getScore(m.id); return s.a !== null && s.b !== null; }).length;
  return '<div class="chips">' +
    '<span class="chip">🎾 ' + DATA.matches.length + ' matches total</span>' +
    '<span class="chip" id="chip-done">✅ ' + nDone + ' results entered</span>' +
    '<span class="chip">📅 Generated: ' + esc(DATA.generated) + '</span>' +
    '</div>' +
    '<div class="card">' +
      '<div class="card-head">📋 All Matches — ' + esc(DATA.season) + '</div>' +
      '<div class="tbl-wrap"><table>' +
        '<thead><tr>' + pHead + '<th>Time</th><th>Terrain</th><th>Team A</th><th>Score</th><th>Team B</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
      '</table></div>' +
    '</div>' +
    '<p class="help">Scores entered here are saved automatically in your browser. ' +
    'Use <strong>Export</strong> to download <code>scores.json</code> and commit it ' +
    'to your GitHub Pages repository so that everyone sees the latest results.</p>';
}

/* ── Poule panel ── */
function buildPoule(poule) {
  const teams = DATA.teams_by_poule[poule] || [];
  const ms = DATA.matches.filter(m => m.poule === poule);
  const total = teams.length * (teams.length - 1) / 2;
  return '<div class="chips">' +
    '<span class="chip">👥 ' + teams.length + ' teams</span>' +
    '<span class="chip">🎾 ' + ms.length + ' / ' + total + ' matches scheduled</span>' +
    '</div>' +
    buildStandingsCard(poule) +
    buildTeamsCard(poule, teams) +
    buildMatchCard(poule, ms);
}

/* ── Standings card ── */
function buildStandingsCard(poule) {
  return '<div class="card">' +
    '<div class="card-head">🏆 Standings — Poule ' + esc(poule) + '</div>' +
    '<div class="card-body" id="standings-' + esc(poule) + '">' + renderStandings(poule) + '</div>' +
    '</div>';
}
function renderStandings(poule) {
  const rows = computeStandings(poule);
  if (rows.every(r => r.p === 0)) {
    return '<p class="s-empty">No results entered yet — add scores in the match schedule below.</p>';
  }
  const trs = rows.map((r, i) =>
    '<tr>' +
      '<td class="s-rank">' + rankSymbol(i) + '</td>' +
      '<td class="s-name">' + esc(r.name) + '</td>' +
      '<td>' + r.p + '</td><td>' + r.w + '</td><td>' + r.d + '</td><td>' + r.l + '</td>' +
      '<td class="s-pts">' + r.pts + '</td>' +
    '</tr>'
  ).join('');
  return '<div class="s-wrap tbl-wrap"><table>' +
    '<thead><tr><th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>Pts</th></tr></thead>' +
    '<tbody>' + trs + '</tbody>' +
    '</table></div>' +
    '<p class="help" style="padding-top:8px">Points: W = 2 &nbsp;·&nbsp; D = 1 &nbsp;·&nbsp; L = 0</p>';
}

/* ── Teams card ── */
function buildTeamsCard(poule, teams) {
  const withDetails = teams.some(t => t.player_1 || t.player_2);
  if (!withDetails) return '';
  const cards = teams.map(t =>
    '<div class="team-card">' +
      '<div class="tc-name">' + esc(t.name) + '</div>' +
      '<div class="tc-detail">' +
        (t.player_1 ? '👤 ' + esc(t.player_1) + (t.tel_1 ? ' · <a href="tel:' + esc(t.tel_1) + '">' + esc(t.tel_1) + '</a>' : '') + '<br>' : '') +
        (t.player_2 ? '👤 ' + esc(t.player_2) + (t.tel_2 ? ' · <a href="tel:' + esc(t.tel_2) + '">' + esc(t.tel_2) + '</a>' : '') : '') +
      '</div>' +
    '</div>'
  ).join('');
  const cbId = 'cb-' + poule;
  const chId = 'ch-' + poule;
  return '<div class="card">' +
    '<div class="card-head collapsible" id="' + chId + '" onclick="toggleCard(\'' + cbId + '\', this)">' +
      '👥 Players — Poule ' + esc(poule) + ' <span class="toggle-icon">▾</span>' +
    '</div>' +
    '<div class="card-body" id="' + cbId + '">' +
      '<div class="teams-grid">' + cards + '</div>' +
    '</div>' +
  '</div>';
}

/* ── Match schedule card ── */
function buildMatchCard(poule, ms) {
  if (!ms.length) return '<p style="color:var(--text-muted);font-style:italic;padding:12px 0">No matches scheduled.</p>';
  const sorted = [...ms].sort((a, b) =>
    a.date !== b.date ? a.date.localeCompare(b.date) : a.time.localeCompare(b.time)
  );
  let rows = '', last = null;
  for (const m of sorted) {
    if (m.date !== last) {
      last = m.date;
      rows += '<tr class="date-row"><td colspan="6">' + esc(fmtDate(m.date)) + '</td></tr>';
    }
    const s = getScore(m.id);
    const va = s.a !== null ? s.a : '', vb = s.b !== null ? s.b : '';
    const res = resultForA(m.id);
    const tr = res === 'w' ? 'winner-a' : res === 'l' ? 'winner-b' : '';
    rows += '<tr class="' + tr + '" data-match-row="' + esc(m.id) + '">' +
      '<td>' + esc(m.time) + '</td>' +
      '<td>' + esc(m.terrain) + '</td>' +
      '<td>' + esc(m.team_a) + '</td>' +
      '<td><div class="score-wrap">' +
        '<input class="score-in" type="number" min="0" max="99" data-match="' + esc(m.id) + '" data-side="a" value="' + va + '" placeholder="—">' +
        '<span class="score-sep">–</span>' +
        '<input class="score-in" type="number" min="0" max="99" data-match="' + esc(m.id) + '" data-side="b" value="' + vb + '" placeholder="—">' +
      '</div></td>' +
      '<td>' + esc(m.team_b) + '</td>' +
      '<td id="res-' + esc(m.id) + '">' + badgeHtml(res) + '</td>' +
    '</tr>';
  }
  return '<div class="card">' +
    '<div class="card-head">📅 Match Schedule — Poule ' + esc(poule) + '</div>' +
    '<div class="tbl-wrap"><table>' +
      '<thead><tr><th>Time</th><th>Terrain</th><th>Team A</th><th>Score</th><th>Team B</th><th>Result</th></tr></thead>' +
      '<tbody>' + rows + '</tbody>' +
    '</table></div>' +
  '</div>';
}

/* ── Collapsible helper ── */
function toggleCard(bodyId, headEl) {
  const body = document.getElementById(bodyId);
  if (!body) return;
  const hidden = body.classList.toggle('hidden');
  headEl.classList.toggle('collapsed', hidden);
}

function applyInterclubFilters() {
  const typeSel = document.getElementById('ic-filter-type');
  const capSel  = document.getElementById('ic-filter-kapitein');
  const ontvSel = document.getElementById('ic-filter-ontv');
  const bevSel  = document.getElementById('ic-filter-bev');
  const tbody   = document.getElementById('interclub-tbody');
  if (!tbody) return;

  const typeNeedle = String(typeSel ? typeSel.value : '').toLowerCase().trim();
  const capNeedle  = String(capSel  ? capSel.value  : '').toLowerCase().trim();
  const ontvNeedle = String(ontvSel ? ontvSel.value : '').toLowerCase().trim();
  const bevNeedle  = String(bevSel  ? bevSel.value  : '').toLowerCase().trim();
  const anyFilter  = typeNeedle || capNeedle || ontvNeedle || bevNeedle;

  let visibleCount = 0;
  tbody.querySelectorAll('tr').forEach(tr => {
    const type = tr.dataset.typeNorm     || '';
    const cap  = tr.dataset.kapiteinNorm || '';
    const ontv = tr.dataset.ontvNorm     || '';
    const bev  = tr.dataset.bevNorm      || '';
    const show = (!typeNeedle || type === typeNeedle)
              && (!capNeedle  || cap  === capNeedle)
              && (!ontvNeedle || ontv === ontvNeedle)
              && (!bevNeedle  || bev  === bevNeedle);
    tr.style.display = show ? '' : 'none';
    if (show) {
      tr.style.backgroundColor = anyFilter
        ? (visibleCount % 2 === 0 ? 'var(--card)' : 'var(--clay-bg)')
        : '';
      visibleCount += 1;
    } else {
      tr.style.backgroundColor = '';
    }
  });

  const empty = document.getElementById('interclub-empty-filter');
  if (empty) empty.style.display = visibleCount ? 'none' : 'block';

  const thType = document.getElementById('ic-th-type');
  const thKap  = document.getElementById('ic-th-kapitein');
  const thOntv = document.getElementById('ic-th-ontv');
  const thBev  = document.getElementById('ic-th-bev');
  if (thType) thType.classList.toggle('th-active-filter', !!typeNeedle);
  if (thKap)  thKap.classList.toggle('th-active-filter',  !!capNeedle);
  if (thOntv) thOntv.classList.toggle('th-active-filter', !!ontvNeedle);
  if (thBev)  thBev.classList.toggle('th-active-filter',  !!bevNeedle);
}

/* ═══════════════════════════════════════════════════════
   Static club info panels — TC Kooike, Kapellen
   ═══════════════════════════════════════════════════════ */
function buildStaticPanel(id) {
  switch (id) {
    case 'welkom':   return panelWelkom();
    case 'kalender': return panelKalender();
    case 'interclub': return panelInterclub();
    case 'bestuur':  return panelBestuur();
    case 'sfeer':    return panelSfeer();
    case 'school':   return panelSchool();
    case 'ladder':   return panelLadder();
    case 'sponsors': return panelSponsors();
    case 'contact':  return panelContact();
    default: return '';
  }
}

function panelWelkom() {
  return '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px">' +
      '<img src="images/sfeer/tennisplezier6.jpg" alt="TC Kooike" style="width:100%;height:200px;object-fit:cover;object-position:center top;border-radius:10px" onerror="this.style.display=\'none\'">' +
      '<img src="images/sfeer/competitie2.jpg" alt="TC Kooike" style="width:100%;height:200px;object-fit:cover;object-position:center center;border-radius:10px" onerror="this.style.display=\'none\'">' +
      '<img src="images/sfeer/sfb13.jpg" alt="TC Kooike" style="width:100%;height:200px;object-fit:cover;object-position:center top;border-radius:10px" onerror="this.style.display=\'none\'">' +
    '</div>' +
    '<div class="card"><div class="card-head">🎾 TC Kooike is ...</div><div class="card-body">' +
      DATA.welkom.intro_html +
    '</div></div>' +
    '<div class="welkom-bottom-grid" style="display:grid;grid-template-columns:2fr 1fr;gap:16px;align-items:stretch">' +
      '<div class="card" style="margin-bottom:0"><div class="card-head">🎾 Hoe reserveren?</div><div class="card-body">' +
        DATA.welkom.reserveren_html +
      '</div></div>' +
      (function() {
        const shuffled = [...SPONSORS].sort(() => Math.random() - 0.5);
        const track = shuffled.map(s => '<img src="' + s.img + '" alt="' + s.name + '" title="' + s.name + '" onerror="this.style.display=\'none\'">').join('');
        return '<div class="card" style="margin-bottom:0;overflow:hidden;display:flex;flex-direction:column"><div class="card-head">🤝 Sponsors</div><div class="card-body" style="padding:12px;flex:1;display:flex;align-items:stretch">' +
          '<div class="marquee-wrap"><div class="marquee-track">' + track + track + '</div></div>' +
          '</div></div>';
      })() +
    '</div>';
}

function panelKalender() {
  const events = DATA.kalender_events || [];
  const now = new Date();
  const rows = events.map(e => {
    const noteVisible = e.note && !(e.hideAfter && now >= new Date(e.hideAfter));
    return '<div class="kal-item"><div class="kal-date">' + esc(e.date) + '</div>' +
      '<div class="kal-desc">' + esc(e.desc) + (noteVisible ? '<small>' + e.note + '</small>' : '') + '</div></div>';
  }).join('');
  return '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px">' +
    '<img src="images/sfeer/plezier5.jpg" alt="" style="width:100%;height:180px;object-fit:cover;object-position:center top;border-radius:7px" onerror="this.style.display=\'none\'">' +
    '<img src="images/kalender/kal2.jpg" alt="" style="width:100%;height:180px;object-fit:cover;object-position:center top;border-radius:7px" onerror="this.style.display=\'none\'">' +
    '<img src="images/kalender/kal_new.jpg" alt="" style="width:100%;height:180px;object-fit:cover;object-position:center top;border-radius:7px" onerror="this.style.display=\'none\'">' +
  '</div>' +
  '<div class="card"><div class="card-head">📅 Evenementen &amp; Activiteiten 2026</div>' +
    '<div class="card-body">' +
    '<div class="kal-grid">' + rows + '</div>' +
    '<p class="help" style="margin-top:14px">Terreinreservaties via ' +
    '<a href="https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/reserveer-een-terrein?clubId=2158" target="_blank">Tennis &amp; Padel Vlaanderen</a>. ' +
    'Lid worden? <a href="https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/lid-worden?clubId=2158" target="_blank">Schrijf je hier in</a>.</p>' +
    '</div></div>';
}

function panelInterclub() {
  const parseInterclubDate = (raw) => {
    const s = String(raw || '').trim();
    const m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?$/);
    if (!m) return null;
    const day = Number(m[1]);
    const month = Number(m[2]);
    const year = Number(m[3]);
    const hour = m[4] ? Number(m[4]) : 0;
    const minute = m[5] ? Number(m[5]) : 0;
    const d = new Date(year, month - 1, day, hour, minute, 0, 0);
    if (Number.isNaN(d.getTime())) return null;
    return d;
  };

  const weekdayNl = ['zon', 'maa', 'din', 'woe', 'don', 'vrij', 'zat'];

  const now = new Date();

  const fmtClub = (name) => {
    const club = String(name || '');
    if (club.toUpperCase().includes('KOOIKE')) {
      return '<strong>' + esc(club) + '</strong>';
    }
    return esc(club);
  };

  const filtered = (DATA.interclub_matches || []).map(m => {
    const dt = parseInterclubDate(m.datum);
    return { m, dt };
  }).filter(x => x.dt && x.dt.getTime() >= now.getTime())
    .sort((a, b) => a.dt.getTime() - b.dt.getTime());

  const capOptions = Array.from(new Set(
    filtered.map(({ m }) => String(m.kapitein || '').trim()).filter(Boolean)
  )).sort((a, b) => a.localeCompare(b, 'nl', { sensitivity: 'base' }))
    .map(name => '<option value="' + esc(name.toLowerCase()) + '">' + esc(name) + '</option>')
    .join('');

  const _buildClubOptions = (key, label) => {
    const all = Array.from(new Set(
      filtered.map(({ m }) => String(m[key] || '').trim()).filter(Boolean)
    ));
    const kooike = all.filter(c => c.toUpperCase().includes('KOOIKE'))
      .sort((a, b) => a.localeCompare(b, 'nl'));
    const rest = all.filter(c => !c.toUpperCase().includes('KOOIKE'))
      .sort((a, b) => a.localeCompare(b, 'nl', { sensitivity: 'base' }));
    const divider = kooike.length && rest.length ? '<option disabled>──────────</option>' : '';
    return [...kooike, ...rest]
      .map((c, i) =>
        (i === kooike.length && kooike.length && rest.length ? '<option disabled>──────────</option>' : '') +
        '<option value="' + esc(c.toLowerCase()) + '">' + esc(c) + '</option>'
      ).join('');
  };

  const ontvOptions = _buildClubOptions('ontvangende_club', 'Ontvangende club');
  const bevOptions  = _buildClubOptions('bezoekende_club',  'Bezoekende club');

  const typeOptions = Array.from(new Set(
    filtered.map(({ m }) => String(m.type || '').trim()).filter(Boolean)
  )).sort()
    .map(t => '<option value="' + esc(t.toLowerCase()) + '">' + esc(t) + '</option>')
    .join('');

  const rows = filtered.map(({ m, dt }) => {
    const prefix = weekdayNl[dt.getDay()] || '';
    const shownDate = (prefix ? prefix + ' ' : '') + String(m.datum || '');
    const typeNorm = String(m.type || '').toLowerCase();
    const kapNorm  = String(m.kapitein || '').toLowerCase();
    const ontvNorm = String(m.ontvangende_club || '').toLowerCase();
    const bevNorm  = String(m.bezoekende_club || '').toLowerCase();
    return '<tr data-type-norm="' + esc(typeNorm) + '" data-kapitein-norm="' + esc(kapNorm) + '" data-ontv-norm="' + esc(ontvNorm) + '" data-bev-norm="' + esc(bevNorm) + '">' +
      '<td>' + esc(shownDate) + '</td>' +
      '<td>' + esc(m.type || '') + '</td>' +
      '<td>' + esc(m.kapitein || '') + '</td>' +
      '<td>' + fmtClub(m.ontvangende_club) + '</td>' +
      '<td>' + fmtClub(m.bezoekende_club) + '</td>' +
    '</tr>';
  }).join('');

  if (!rows) {
    return '<div class="card"><div class="card-head">🎾 Interclub</div><div class="card-body">' +
      '<p class="help">Geen toekomstige interclubgegevens gevonden in het Excel-bestand.</p>' +
      '</div></div>';
  }

  return '<div class="card"><div class="card-head">🎾 Komende interclubontmoetingen</div><div class="card-body">' +
    '<div class="tbl-wrap"><table>' +
    '<thead><tr>' +
      '<th>Datum</th>' +
      '<th id="ic-th-type">' +
        '<select id="ic-filter-type" class="th-filter" onchange="applyInterclubFilters()" title="Filter op type">' +
          '<option value="">Type ▾</option>' +
          typeOptions +
        '</select>' +
      '</th>' +
      '<th id="ic-th-kapitein">' +
        '<select id="ic-filter-kapitein" class="th-filter" onchange="applyInterclubFilters()" title="Filter op kapitein">' +
          '<option value="">Kapitein ▾</option>' +
          capOptions +
        '</select>' +
      '</th>' +
      '<th id="ic-th-ontv">' +
        '<select id="ic-filter-ontv" class="th-filter" onchange="applyInterclubFilters()" title="Filter op ontvangende club">' +
          '<option value="">Ontvangende club ▾</option>' +
          ontvOptions +
        '</select>' +
      '</th>' +
      '<th id="ic-th-bev">' +
        '<select id="ic-filter-bev" class="th-filter" onchange="applyInterclubFilters()" title="Filter op bezoekende club">' +
          '<option value="">Bezoekende club ▾</option>' +
          bevOptions +
        '</select>' +
      '</th>' +
    '</tr></thead>' +
    '<tbody id="interclub-tbody">' + rows + '</tbody>' +
    '</table></div>' +
    '<p id="interclub-empty-filter" class="help" style="display:none;margin-top:10px">Geen wedstrijden gevonden voor deze filter.</p>' +
    '</div></div>';
}

function panelBestuur() {
  const board = DATA.bestuur || [];
  const initials = name => name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0,2);
  const cards = board.map(b =>
    '<div class="board-card">' +
      (b.img
        ? '<img class="board-photo" src="' + esc(b.img) + '" alt="' + esc(b.name) + '" onerror="this.replaceWith(Object.assign(document.createElement(\'div\'),{className:\'board-photo board-initials\',textContent:\''+initials(b.name)+'\'}))" >'
        : '<div class="board-photo board-initials">' + initials(b.name) + '</div>') +
      '<div class="board-info"><div class="board-name">' + esc(b.name) + '</div>' +
      '<div class="board-role">' + esc(b.role) + '</div></div>' +
    '</div>'
  ).join('');
  return '<div class="card"><div class="card-head">👥 Dagelijks Bestuur</div>' +
    '<div class="card-body">' +
    '<div class="board-grid">' + cards + '</div>' +
    '<p class="help" style="margin-top:14px">Vragen of opmerkingen? ' +
    '<a href="mailto:tckooike@gmail.com">tckooike@gmail.com</a> · ' +
    '<a href="tel:+32497891454">+32 497 89 14 54 (Steven)</a>' +
    '</div></div>' +
    '<div class="card" style="margin-top:16px"><div class="card-head">📋 Huishoudelijk Reglement</div><div class="card-body" style="max-height:520px;overflow-y:auto;font-size:.88rem;line-height:1.75;color:var(--text)">' +
      DATA.reglement_html +
      '</div></div>';
}

function panelSfeer() {
  const sfeerImgs = DATA.sfeer || [];
  for (let i = sfeerImgs.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [sfeerImgs[i], sfeerImgs[j]] = [sfeerImgs[j], sfeerImgs[i]];
  }
  const gallery = sfeerImgs.map(o =>
    '<a href="images/sfeer/full/' + o.f + '.jpg" class="lb-trigger" aria-label="' + esc(o.c || 'Sfeerbeeld') + '">' +
    '<img src="images/sfeer/' + o.f + '.jpg" alt="' + esc(o.c) + '"' + (o.pos ? ' style="object-position:' + o.pos + '"' : '') + ' onerror="this.parentElement.style.display=\'none\'">' +
    '</a>'
  ).join('');
  return '<div class="card"><div class="card-head">📸 Sfeerbeelden</div>' +
    '<div class="card-body">' +
    '<p style="margin-bottom:14px;font-size:.88rem;color:var(--text-muted)">' +
    '… een club voor iedereen &nbsp;·&nbsp; tennisplezier &nbsp;·&nbsp; winnaars &nbsp;·&nbsp; bekende gezichten &nbsp;·&nbsp; een groot ❤️</p>' +
    '<div class="photo-gallery">' + gallery + '</div>' +
    '</div></div>';
}

function panelSchool() {
  const sections = DATA.school || [];
  const cards = sections.map(s =>
    '<div class="card" style="margin-bottom:16px">' +
    (s.heading ? '<div class="card-head">' + esc(s.heading) + '</div>' : '') +
    '<div class="card-body">' + s.html + '</div>' +
    '</div>'
  ).join('');
  return '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px">' +
    '<img src="images/school/whackit.jpg" alt="WhackIt" style="width:100%;height:180px;object-fit:contain;background:#f9f9f9;border-radius:10px" onerror="this.style.display=\'none\'">' +
    '<img src="images/school/school3.jpg" alt="" style="width:100%;height:180px;object-fit:cover;object-position:center top;border-radius:10px" onerror="this.style.display=\'none\'">' +
    '<img src="images/school/school4.jpg" alt="" style="width:100%;height:180px;object-fit:cover;object-position:center top;border-radius:10px" onerror="this.style.display=\'none\'">' +
  '</div>' + cards;
}

function panelLadder() {
  return '<div class="card"><div class="card-head">🪜 Laddercompetitie — Hoe werkt het?</div><div class="card-body">' +
    '<picture><source srcset="images/ladder/ladder.webp" type="image/webp"><img src="images/ladder/ladder.png" alt="Laddercompetitie" class="ladder-img" onerror="this.style.display=\'none\'"></picture>' +
    DATA.ladder_html +
    '</div></div>';
}

function panelSponsors() {
  // Verified logo↔link mapping from tckooike.wordpress.com/sponsors/ (April 2026)
  // BDV Windows and Mitch Peeters share the same logo image on the WordPress site.
  // Files 31-1, 32, 35-36-37-38-39 appear on the page but without hyperlinks.
  const sponsors = SPONSORS;
  const logos = [...sponsors].sort(() => Math.random() - 0.5).map(s =>
    s.url
      ? '<a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer" title="' + esc(s.name) + '">' +
          '<img src="' + esc(s.img) + '" alt="' + esc(s.name) + '" onerror="this.closest(\'a\').style.display=\'none\'">' +
        '</a>'
      : '<div style="display:flex;align-items:center;justify-content:center;padding:0;border:1px solid var(--border);border-radius:8px;background:#fff;height:160px;box-sizing:border-box;overflow:hidden">' +
          '<img src="' + esc(s.img) + '" alt="' + esc(s.name) + '" style="width:100%;height:100%;object-fit:contain" onerror="this.parentElement.style.display=\'none\'">' +
        '</div>'
  ).join('');
  return '<div class="card"><div class="card-head">🤝 Onze Sponsors</div><div class="card-body">' +
    '<p style="margin-bottom:14px;font-size:.88rem;color:var(--text-muted)">TC Kooike kan rekenen op een geweldige groep sponsors. ' +
    'Steun onze sponsors door hun logo aan te klikken!</p>' +
    '<div class="sponsor-logo-grid">' + logos + '</div>' +
    '<p class="help" style="margin-top:16px">Wil je ook sponsor worden? Stuur een mailtje naar <a href="mailto:tckooike@gmail.com">tckooike@gmail.com</a> of neem contact op met Steven (<a href="tel:+32497891454">+32 497 89 14 54</a>).</p>' +
    '</div></div>';
}

function panelContact() {
  const sections = DATA.contact_sections || [];
  const cards = sections.map(s =>
    '<div class="info-card"><h3>' + esc(s.heading) + '</h3>' +
    '<div class="contact-block">' + s.html + '</div></div>'
  ).join('');
  return '<div class="card"><div class="card-head">📞 Contact & Locatie — TC Kooike</div><div class="card-body">' +
    '<div class="info-grid">' + cards + '</div>' +
    '<div style="margin-top:14px;border-radius:8px;overflow:hidden;border:1px solid var(--border)">' +
    '<iframe src="https://www.google.com/maps?q=Ertbrandstraat+58,+2920+Kapellen,+Belgium&output=embed" ' +
    'width="100%" height="320" style="border:0;display:block" allowfullscreen loading="lazy"></iframe>' +
    '</div>' +
    '</div></div>';
}


/* ═══════════════════════════════════════════════════════
   Event handling
   ═══════════════════════════════════════════════════════ */
function onScoreChange(e) {
  const inp = e.target;
  setScore(inp.dataset.match, inp.dataset.side, inp.value);
  refreshMatch(inp.dataset.match);
}
function refreshMatch(id) {
  const s = getScore(id);
  const res = resultForA(id);
  const trCls = res === 'w' ? 'winner-a' : res === 'l' ? 'winner-b' : '';
  document.querySelectorAll('[data-match-row="' + CSS.escape(id) + '"]').forEach(tr => {
    tr.className = trCls;
    ['a', 'b'].forEach(side => {
      tr.querySelectorAll('.score-in[data-side="' + side + '"]').forEach(inp => {
        const cur = s[side] !== null ? String(s[side]) : '';
        if (inp.value !== cur) inp.value = cur;
      });
    });
  });
  const badge = document.getElementById('res-' + CSS.escape(id));
  if (badge) badge.innerHTML = badgeHtml(res);
  const match = DATA.matches.find(m => m.id === id);
  if (match) {
    const el = document.getElementById('standings-' + CSS.escape(match.poule));
    if (el) el.innerHTML = renderStandings(match.poule);
  }
  const chip = document.getElementById('chip-done');
  if (chip) {
    const n = DATA.matches.filter(m => { const s = getScore(m.id); return s.a !== null && s.b !== null; }).length;
    chip.textContent = '✅ ' + n + ' results entered';
  }
}
function refreshAll() {
  for (const m of DATA.matches) refreshMatch(m.id);
}

/* ═══════════════════════════════════════════════════════
   Init
   ═══════════════════════════════════════════════════════ */
async function init() {
  document.getElementById('js-title').textContent = DATA.club_name;
  document.title = DATA.club_name;
  loadLocal();
  buildNav();
  buildAllPanels();
  document.getElementById('btn-export').addEventListener('click', exportScores);
  document.getElementById('btn-import-trigger').addEventListener('click', () =>
    document.getElementById('file-import').click()
  );
  document.getElementById('file-import').addEventListener('change', e => {
    if (e.target.files[0]) importScores(e.target.files[0]);
    e.target.value = '';
  });
  // Lightbox
  const overlay = document.getElementById('lb-overlay');
  const lbImg   = document.getElementById('lb-img');
  function lbOpen(src, alt) { lbImg.src = src; lbImg.alt = alt; overlay.classList.add('open'); }
  function lbClose() { overlay.classList.remove('open'); lbImg.src = ''; }
  document.getElementById('lb-close').addEventListener('click', lbClose);
  overlay.addEventListener('click', e => { if (e.target === overlay) lbClose(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') lbClose(); });
  document.addEventListener('click', e => {
    const a = e.target.closest('a.lb-trigger');
    if (!a) return;
    e.preventDefault();
    lbOpen(a.href, a.getAttribute('aria-label') || '');
  });
  await fetchServerScores();
  refreshAll();
}
document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>"""


def build(schedule_data: dict, path: str = 'docs/index.html') -> None:
    """Assemble the full site from schedule data + markdown input files."""
    data = {
        **schedule_data,
        'generated':       schedule_data.get('generated') or str(_date.today()),
        'interclub_matches': load_interclub_matches(),
        'kalender_events':   load_kalender_events(),
        'sponsors':          load_sponsors(),
        'reglement_html':    load_reglement(),
        'bestuur':           load_bestuur(),
        'welkom':            load_welkom(),
        'school':            load_school(),
        'ladder_html':       load_ladder(),
        'contact_sections':  load_contact(),
        'sfeer':             load_sfeer(),
    }
    html = _HTML_TEMPLATE.replace('__SCHEDULE_DATA__', json.dumps(data, ensure_ascii=False))
    Path(path).write_text(html, encoding='utf-8')
    print(f'Built {path}')

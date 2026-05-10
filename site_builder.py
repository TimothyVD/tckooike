from __future__ import annotations

import json
import re
from datetime import date as _date
from pathlib import Path

import markdown
from markdown.treeprocessors import Treeprocessor


def _strip_comments(text: str) -> str:
    """Remove comment lines (starting with //) from markdown text."""
    return '\n'.join(
        line for line in text.splitlines()
        if not line.lstrip().startswith('//')
    )


class _TargetBlankProcessor(Treeprocessor):
    def run(self, root):
        for el in root.iter('a'):
            href = el.get('href', '')
            if not href.startswith(('mailto:', 'tel:')):
                el.set('target', '_blank')


class _TargetBlankExtension(markdown.Extension):
    def extendMarkdown(self, md):
        md.treeprocessors.register(_TargetBlankProcessor(md), 'target_blank', 5)


_md = markdown.Markdown(extensions=[_TargetBlankExtension()])


def _md_inline(text: str) -> str:
    """Convert inline Markdown (bold, links) to HTML using python-markdown."""
    result = _md.convert(text)
    _md.reset()
    if result.startswith('<p>') and result.endswith('</p>'):
        result = result[3:-4]
    return result


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
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
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
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
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
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
    return _md_to_html(text, intro_style=True)


def load_bestuur(path: str = "input/bestuur.md") -> list[dict]:
    """Load board members from a Markdown file.

    Format:
      - Naam | Rol | images/bestuur/foto.jpg   (foto is optional)
    """
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
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
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
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
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
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
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
    return _md_to_html(text)


def load_contact(path: str = "input/contact.md") -> list[dict]:
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
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
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
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
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
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

_TEMPLATE_PATH = Path(__file__).parent / "site_template.html"

def _load_template() -> str:
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


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
    html = _load_template().replace('__SCHEDULE_DATA__', json.dumps(data, ensure_ascii=False))
    Path(path).write_text(html, encoding='utf-8')
    print(f'Built {path}')

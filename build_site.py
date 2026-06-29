#!/usr/bin/env python3
"""Lightweight site builder — no heavy dependencies required.

Reads input/schedule.md (the hand-editable schedule source — see its header
comment to reschedule a match) and all input/*.md files, then writes
docs/index.html. input/schedule.json is regenerated from schedule.md here
too, since sync_results_db.py and other tools still read it — don't hand-edit
schedule.json, it's a generated file now, just like docs/index.html.

Also auto-generates missing thumbnails from docs/images/sfeer/*.jpg into
docs/images/sfeer/thumbnails/ (requires Pillow).

Run locally:
    python build_site.py

GitHub Actions runs this automatically on every push that touches input/.
"""
import json
from pathlib import Path

import site_builder

SCHEDULE_MD = Path("input/schedule.md")
SCHEDULE_JSON = Path("input/schedule.json")
OUTPUT = "docs/index.html"
SFEER_DIR = Path("docs/images/sfeer")
THUMB_DIR = SFEER_DIR / "thumbnails"
THUMB_MAX = (600, 400)
THUMB_QUALITY = 80

CLUB_NAME = "TC Kooike"
SEASON = "Seizoen 2026"

EMPTY_SCHEDULE = {
    "club_name":      CLUB_NAME,
    "season":         SEASON,
    "poules":         [],
    "teams_by_poule": {},
    "matches":        [],
}


def generate_missing_thumbnails() -> None:
    """Create a thumbnail for every full-size image in sfeer/ that lacks one."""
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    missing = [f for f in sorted(SFEER_DIR.glob("*.jpg")) if not (THUMB_DIR / f.name).exists()]
    if not missing:
        return
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed — skipping thumbnail generation.  pip install Pillow")
        return
    for src in missing:
        dst = THUMB_DIR / src.name
        img = Image.open(src)
        img.thumbnail(THUMB_MAX, Image.LANCZOS)
        img.save(dst, "JPEG", quality=THUMB_QUALITY, optimize=True)
        print(f"  thumbnail: {src.name} ({src.stat().st_size // 1024}KB → {dst.stat().st_size // 1024}KB)")
    print(f"Generated {len(missing)} thumbnail(s) in {THUMB_DIR}")


generate_missing_thumbnails()

if SCHEDULE_MD.exists():
    schedule_data = site_builder.load_schedule_md(str(SCHEDULE_MD))
    schedule_data["club_name"] = CLUB_NAME
    schedule_data["season"] = SEASON
    SCHEDULE_JSON.write_text(
        json.dumps(schedule_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Regenerated {SCHEDULE_JSON} from {SCHEDULE_MD}")
elif SCHEDULE_JSON.exists():
    schedule_data = json.loads(SCHEDULE_JSON.read_text(encoding="utf-8"))
else:
    schedule_data = EMPTY_SCHEDULE

site_builder.build(schedule_data, OUTPUT)

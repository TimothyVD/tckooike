#!/usr/bin/env python3
"""Lightweight site builder — no heavy dependencies required.

Reads input/schedule.json (produced by competition_scheduler.py) and all
input/*.md files, then writes docs/index.html.

Also auto-generates missing thumbnails from docs/images/sfeer/*.jpg into
docs/images/sfeer/thumbnails/ (requires Pillow).

Run locally:
    python build_site.py

GitHub Actions runs this automatically on every push that touches input/.
"""
import json
from pathlib import Path

import site_builder

SCHEDULE_JSON = Path("input/schedule.json")
OUTPUT = "docs/index.html"
SFEER_DIR = Path("docs/images/sfeer")
THUMB_DIR = SFEER_DIR / "thumbnails"
THUMB_MAX = (600, 400)
THUMB_QUALITY = 80

EMPTY_SCHEDULE = {
    "club_name":      "TC Kooike",
    "season":         "Seizoen 2026",
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

schedule_data = (
    json.loads(SCHEDULE_JSON.read_text(encoding="utf-8"))
    if SCHEDULE_JSON.exists()
    else EMPTY_SCHEDULE
)

site_builder.build(schedule_data, OUTPUT)

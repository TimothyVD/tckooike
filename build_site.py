#!/usr/bin/env python3
"""Lightweight site builder — no heavy dependencies required.

Reads input/schedule.json (produced by competition_scheduler.py) and all
input/*.md files, then writes docs/index.html.

Run locally:
    python build_site.py

GitHub Actions runs this automatically on every push that touches input/.
"""
import json
from pathlib import Path

import site_builder

SCHEDULE_JSON = Path("input/schedule.json")
OUTPUT = "docs/index.html"

EMPTY_SCHEDULE = {
    "club_name":      "TC Kooike",
    "season":         "Seizoen 2026",
    "poules":         [],
    "teams_by_poule": {},
    "matches":        [],
}

schedule_data = (
    json.loads(SCHEDULE_JSON.read_text(encoding="utf-8"))
    if SCHEDULE_JSON.exists()
    else EMPTY_SCHEDULE
)

site_builder.build(schedule_data, OUTPUT)

#!/usr/bin/env python3
"""
Generate per-team Supabase access codes and push matches/teams to the DB.

Run locally, after competition_scheduler.py has produced input/schedule.json
and input/teams.csv holds the current team roster. Re-running is safe and
idempotent — existing access codes are never regenerated, so previously
distributed codes keep working after a re-schedule.

Installation
-------------
    pip install -r requirements-sync.txt

Usage
------
    export SUPABASE_URL=https://your-project.supabase.co
    export SUPABASE_SERVICE_ROLE_KEY=...          # never commit this
    python sync_results_db.py
"""
import csv
import json
import os
import random
import string
import sys
from pathlib import Path

TEAMS_CSV = Path("input/teams.csv")
SCHEDULE_JSON = Path("input/schedule.json")

# Exclude visually-ambiguous characters so codes are easy to read/type
# when shared over WhatsApp etc.
_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")
_CODE_LEN = 6


def gen_code() -> str:
    return "".join(random.choices(_ALPHABET, k=_CODE_LEN))


def team_name(row: dict) -> str:
    """Must match _make_team_name() in competition_scheduler.py exactly."""
    p1 = row.get("player_1", "").strip()
    p2 = row.get("player_2", "").strip()
    if p1 and p2:
        return f"{p1} & {p2}"
    return p1 or p2 or row.get("Team", "").strip()


def load_teams_csv() -> tuple[list[dict], list[str]]:
    with TEAMS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return rows, fieldnames


def ensure_access_codes(rows: list[dict], fieldnames: list[str]) -> tuple[list[str], dict[str, str]]:
    """Adds an access_code to any row lacking one. Returns (fieldnames, {team: new_plaintext_code})."""
    if "access_code" not in fieldnames:
        fieldnames = fieldnames + ["access_code"]

    existing_codes = {row.get("access_code", "").strip() for row in rows if row.get("access_code", "").strip()}
    new_codes: dict[str, str] = {}

    for row in rows:
        if row.get("access_code", "").strip():
            continue
        code = gen_code()
        while code in existing_codes:
            code = gen_code()
        existing_codes.add(code)
        row["access_code"] = code
        new_codes[team_name(row)] = code

    return fieldnames, new_codes


def write_teams_csv(rows: list[dict], fieldnames: list[str]) -> None:
    with TEAMS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def push_to_supabase(rows: list[dict], schedule: dict) -> None:
    import bcrypt
    import requests

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables first.")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    def upsert(table: str, payload: list[dict], on_conflict: str) -> None:
        r = requests.post(
            f"{url}/rest/v1/{table}?on_conflict={on_conflict}",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if not r.ok:
            sys.exit(f"Upsert into {table} failed ({r.status_code}): {r.text}")

    # Every match is pushed, including ones with no date/time yet ("nog te
    # plannen"): teams can schedule those straight from the site via
    # reschedule_match(), which needs the row present to verify the access code
    # and to satisfy the reschedules foreign key. Unscheduled matches get a
    # far-future placeholder slot (the site never shows it — it reads the real
    # date from schedule.json / the reschedules override, not from here).
    UNSCHEDULED_DATE = "2099-12-31"
    UNSCHEDULED_TIME = "00:00"
    matches_payload = [
        {
            "match_id": m["id"],
            "poule": m["poule"],
            "match_date": m["date"] or UNSCHEDULED_DATE,
            "match_time": m["time"] or UNSCHEDULED_TIME,
            "terrain": m.get("terrain", ""),
            "team_a": m["team_a"],
            "team_b": m["team_b"],
        }
        for m in schedule["matches"]
    ]
    upsert("matches", matches_payload, "match_id")
    print(f"Upserted {len(matches_payload)} matches.")

    # Match ids embed date/time, so a re-schedule that moves a match to a
    # different slot leaves its old id behind as an orphan — clean those up
    # so nobody can submit a result against a slot that no longer exists.
    current_ids = {m["match_id"] for m in matches_payload}
    r = requests.get(f"{url}/rest/v1/matches?select=match_id", headers=headers, timeout=30)
    if not r.ok:
        sys.exit(f"Fetching existing matches failed ({r.status_code}): {r.text}")
    stale_ids = [row["match_id"] for row in r.json() if row["match_id"] not in current_ids]
    if stale_ids:
        # Matches with an already-submitted result can't be deleted (FK
        # constraint) — that's deliberate: it surfaces the conflict instead
        # of silently discarding a real result. Delete one at a time so a
        # stuck row doesn't block cleanup of the rest.
        deleted, blocked = 0, []
        for mid in stale_ids:
            dr = requests.delete(
                f"{url}/rest/v1/matches",
                headers=headers,
                params={"match_id": f"eq.{mid}"},
                timeout=30,
            )
            if dr.ok:
                deleted += 1
            else:
                blocked.append(mid)
        print(f"Removed {deleted} stale match row(s) from old schedules.")
        if blocked:
            print(f"WARNING: {len(blocked)} stale match(es) could not be removed "
                  f"(likely have a submitted result attached) — check manually: {blocked}")

    teams_payload = []
    for row in rows:
        name = team_name(row)
        code = row.get("access_code", "").strip()
        poule = row.get("Poule", "").strip() or row.get("poule", "").strip()
        if not name or not code:
            continue
        # Python's bcrypt defaults to the "$2b$" version marker, but this
        # Supabase project's pgcrypto crypt() only matches "$2a$" hashes —
        # algorithmically identical for normal inputs, just an old marker.
        code_hash = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode().replace("$2b$", "$2a$", 1)
        teams_payload.append({"team_name": name, "poule": poule, "access_code_hash": code_hash})
    upsert("teams", teams_payload, "team_name")
    print(f"Upserted {len(teams_payload)} teams.")


def main():
    if not TEAMS_CSV.exists():
        sys.exit(f"{TEAMS_CSV} not found.")
    if not SCHEDULE_JSON.exists():
        sys.exit(f"{SCHEDULE_JSON} not found — run competition_scheduler.py first.")

    rows, fieldnames = load_teams_csv()
    fieldnames, new_codes = ensure_access_codes(rows, fieldnames)
    write_teams_csv(rows, fieldnames)

    schedule = json.loads(SCHEDULE_JSON.read_text(encoding="utf-8"))
    push_to_supabase(rows, schedule)

    if new_codes:
        print("\n" + "=" * 60)
        print("NEW ACCESS CODES — copy these out now, they will not be shown again:")
        print("=" * 60)
        for team, code in sorted(new_codes.items()):
            print(f"  {team:50s} {code}")
        print("=" * 60)
    else:
        print("No new teams without an access code — nothing new to distribute.")


if __name__ == "__main__":
    main()

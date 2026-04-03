#!/usr/bin/env python3
"""
Poule Competition Scheduler
============================
Loads team availabilities from a Google Forms CSV export and terrain slot
definitions, then schedules all round-robin matches optimally using CP-SAT.

Constraints enforced
---------------------
- Both teams must be available at the assigned slot.
- Each (slot, terrain) pair is used by at most one match.
- Each team plays at most one match per day.
- Every match is scheduled at most once.

Objective
----------
Maximise the number of scheduled matches (minimise unscheduled ones).

Installation
-------------
    pip install ortools pandas openpyxl

Google Forms setup (recommended)
----------------------------------
Create a form with:
  - Short answer question: "Team name"
  - Checkbox grid question: rows = dates, columns = time slots
    → Export responses as CSV (Google Sheets → File → Download → CSV)

Usage
------
    python competition_scheduler.py                        # runs built-in demo
    python competition_scheduler.py --teams teams.csv \\
           --avail team_availabilities.csv \\
           --slots terrain_slots.csv \\
           --output schedule.xlsx
"""

from __future__ import annotations

import argparse
import random
from itertools import combinations
from pathlib import Path

import pandas as pd
from ortools.sat.python import cp_model


# ── Constants ──────────────────────────────────────────────────────────────────

SLOT_DURATION_MIN = 90  # minutes per match slot (1h30)

# Truthy strings recognised in the availability CSV
_TRUTHY = {"true", "checked", "yes", "oui", "1", "x", "✓"}


# ── Input loading ──────────────────────────────────────────────────────────────

def load_team_availabilities(csv_path: str) -> dict[str, set[str]]:
    """
    Load team availabilities from a Google Forms checkbox-grid CSV export.

    Expected CSV layout
    --------------------
    Two supported formats:

    Format A — checkbox grid (one column per slot):
        Team,2026-05-04 18:00,2026-05-04 19:30,2026-05-11 18:00,...
        Alpha,TRUE,,TRUE,...
        Bravo,,TRUE,TRUE,...

    Format B — multi-select (selected slots comma-separated in one cell):
        Team,Available slots
        Alpha,"2026-05-04 18:00, 2026-05-11 18:00"
        Bravo,"2026-05-04 19:30"

    The column named "Team" (case-insensitive) holds team names; every other
    column is treated as a slot label or a multi-select availability field.

    Slot labels must match those used in the terrain slots definition
    (format: "YYYY-MM-DD HH:MM").

    Returns
    --------
    {team_name: {slot_label, ...}}
    """
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    # Find the team-name column (case-insensitive)
    team_col = next(
        (c for c in df.columns if c.strip().lower() == "team"), df.columns[0]
    )
    other_cols = [c for c in df.columns if c != team_col]

    availabilities: dict[str, set[str]] = {}

    for _, row in df.iterrows():
        team = row[team_col].strip()
        if not team:
            continue

        available: set[str] = set()

        if len(other_cols) == 1:
            # Format B: comma-separated slot list in a single cell
            raw = row[other_cols[0]]
            for slot in raw.split(","):
                s = slot.strip()
                if s:
                    available.add(s)
        else:
            # Format A: one column per slot, truthy value = available
            for col in other_cols:
                if row[col].strip().lower() in _TRUTHY:
                    available.add(col.strip())

        availabilities[team] = available

    return availabilities


def load_terrain_slots(csv_path: str) -> list[dict]:
    """
    Load terrain slot definitions from a CSV file.

    Expected CSV columns
    ----------------------
        date        YYYY-MM-DD
        time        HH:MM
        terrain_id  integer (1, 2, 3, …)

    Example
    --------
        date,time,terrain_id
        2026-05-04,18:00,1
        2026-05-04,18:00,2
        2026-05-04,19:30,1
        ...

    Returns
    --------
    List of dicts with keys: slot ("YYYY-MM-DD HH:MM"), date, terrain ("T1"…).
    """
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    df["slot"] = df["date"].str.strip() + " " + df["time"].str.strip()
    df["terrain"] = "T" + df["terrain_id"].str.strip()
    return df[["slot", "date", "terrain"]].to_dict("records")


def generate_terrain_slots(
    dates: list[str],
    times: list[str],
    n_terrains: int = 4,
    terrain_overrides: dict[str, int] | None = None,
) -> list[dict]:
    """
    Programmatically generate terrain slots.

    Parameters
    -----------
    dates           List of date strings, e.g. ["2026-05-04", "2026-05-11"]
    times           Time strings per day, e.g. ["18:00", "19:30", "21:00"]
    n_terrains      Default number of terrains per slot
    terrain_overrides  Per-date override: {"2026-05-04": 2} → only 2 terrains
    """
    overrides = terrain_overrides or {}
    slots = []
    for date in dates:
        n = overrides.get(date, n_terrains)
        for time in times:
            for t in range(1, n + 1):
                slots.append(
                    {"slot": f"{date} {time}", "date": date, "terrain": f"T{t}"}
                )
    return slots


def _make_team_name(player_1: str, player_2: str) -> str:
    """
    Build a display team name from two player name strings.

    Format: "<FirstName> <LastInitial> & <FirstName> <LastInitial>"
    Example: "Alice Dupont" + "Bob Martin"  →  "Alice D & Bob M"

    Falls back gracefully when names have no surname or are blank.
    """
    def _fmt(name: str) -> str:
        parts = name.strip().split()
        if not parts:
            return ""
        first = parts[0]
        initial = parts[-1][0].upper() + "." if len(parts) > 1 else ""
        return f"{first} {initial}".strip()

    a = _fmt(player_1)
    b = _fmt(player_2)
    if a and b:
        return f"{a} & {b}"
    return a or b


def load_teams(csv_path: str) -> tuple[dict[str, list[str]], pd.DataFrame]:
    """
    Load team names, poule assignments, and optional player metadata from a CSV.
    Column order is flexible — columns are matched by name (case-insensitive).

    Required column
    ----------------
        team               Team name (optional when player_1 and player_2 are
                           both present — auto-generated as "FirstName L & FirstName L")

    Optional columns (any subset, in any order)
    ---------------------------------------------
        poule              Poule/group identifier (defaults to "A" if absent)
        player_1           Name of first player
        player_2           Name of second player
        ranking_player_1   Ranking / level of player 1
        ranking_player_2   Ranking / level of player 2
        tel_player_1       Phone number of player 1
        tel_player_2       Phone number of player 2

    Returns
    --------
    (poules, team_info_df)
      poules        {poule_name: [team1, team2, …]}
      team_info_df  Full DataFrame with all columns, normalised column names,
                    sorted by Poule then Team — for writing to the Teams sheet.
    """
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    # Normalise column names: strip whitespace, lower-case for lookup
    col_map = {c.strip().lower(): c for c in df.columns}

    def _find(name: str):
        return col_map.get(name)

    team_col  = _find("team")
    if team_col is None:
        team_col = df.columns[0]  # fall back to first column
    poule_col = _find("poule")

    # Canonical display names for known extra columns (order defines sheet column order)
    _KNOWN_EXTRAS = [
        ("poule",            "Poule"),
        ("player_1",         "Player 1"),
        ("player_2",         "Player 2"),
        ("ranking_player_1", "Ranking P1"),
        ("ranking_player_2", "Ranking P2"),
        ("tel_player_1",     "Tel P1"),
        ("tel_player_2",     "Tel P2"),
    ]

    poules: dict[str, list[str]] = {}
    info_rows = []

    p1_col = _find("player_1")
    p2_col = _find("player_2")

    for _, row in df.iterrows():
        p1 = row[p1_col].strip() if p1_col else ""
        p2 = row[p2_col].strip() if p2_col else ""

        # Auto-generate team name from players when both are present;
        # fall back to the explicit Team column value otherwise.
        if p1 and p2:
            team = _make_team_name(p1, p2)
        else:
            team = row[team_col].strip() if team_col else ""
        if not team:
            continue
        poule = row[poule_col].strip() if poule_col else "A"
        if not poule:
            poule = "A"
        poules.setdefault(poule, []).append(team)

        info = {"Team": team}
        for key, display in _KNOWN_EXTRAS:
            src = _find(key)
            info[display] = row[src].strip() if src else ""
        info_rows.append(info)

    # Build display DataFrame with canonical column order, drop empty columns
    display_cols = ["Team"] + [display for _, display in _KNOWN_EXTRAS]
    team_info_df = pd.DataFrame(info_rows, columns=display_cols)
    # Remove columns that are entirely empty (not provided in the source CSV)
    team_info_df = team_info_df.loc[:, (team_info_df != "").any(axis=0)]
    team_info_df = team_info_df.sort_values(["Poule", "Team"] if "Poule" in team_info_df.columns else ["Team"]).reset_index(drop=True)

    return poules, team_info_df


def load_interclub_matches(
    candidates: list[str] | None = None,
    club_keyword: str = "KOOIKE",
) -> list[dict[str, str]]:
    """Load Interclub rows from Excel and map the required website table fields."""
    paths = candidates or [
        "input/tv_interclub_2026.xlsx",
        "input/tv_interclubkalender_2026.xlsx",
    ]

    xlsx_path = next((Path(p) for p in paths if Path(p).exists()), None)
    if xlsx_path is None:
        return []

    df = pd.read_excel(xlsx_path)

    def _pick_col(options: list[str]) -> str | None:
        for opt in options:
            if opt in df.columns:
                return opt
        return None

    date_off_col = _pick_col(["Officiële datum", "Officiele datum", "Officiële speeldatum", "Officiele speeldatum"])
    date_mod_col = _pick_col(["Gewijzigde datum", "Gewijzigde speeldatum"])
    reeks_col = _pick_col(["Reeks"])
    club_a_col = _pick_col(["Club"])
    club_b_col = _pick_col(["Club.1"])
    kap_a_col = _pick_col(["Kapitein"])
    kap_b_col = _pick_col(["Kapitein.1"])

    def _clean(v) -> str:
        if pd.isna(v):
            return ""
        s = str(v).strip()
        if s.lower() in {"nan", "nat"}:
            return ""
        return s

    def _fmt_date(v) -> str:
        if pd.isna(v):
            return ""
        if isinstance(v, pd.Timestamp):
            return v.strftime("%d/%m/%Y %H:%M")
        s = str(v).strip()
        if s.lower() in {"nan", "nat", ""}:
            return ""
        return s

    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        club_a = _clean(row.get(club_a_col, "")) if club_a_col else ""
        club_b = _clean(row.get(club_b_col, "")) if club_b_col else ""

        # Keep only fixtures where TC Kooike appears in either club column.
        in_a = club_keyword in club_a.upper()
        in_b = club_keyword in club_b.upper()
        if not (in_a or in_b):
            continue

        date_mod = _fmt_date(row.get(date_mod_col, "")) if date_mod_col else ""
        date_off = _fmt_date(row.get(date_off_col, "")) if date_off_col else ""
        datum = date_mod or date_off

        kap_a = _clean(row.get(kap_a_col, "")) if kap_a_col else ""
        kap_b = _clean(row.get(kap_b_col, "")) if kap_b_col else ""
        kapitein = kap_a if in_a else (kap_b if in_b else "")

        rows.append({
            "datum": datum,
            "reeks": _clean(row.get(reeks_col, "")) if reeks_col else "",
            "kapitein": kapitein,
            "ontvangende_club": club_a,
            "bezoekende_club": club_b,
        })

    return rows


# ── Core scheduler ─────────────────────────────────────────────────────────────

def schedule(
    poules: dict[str, list[str]],
    team_avail: dict[str, set[str]],
    terrain_slots: list[dict],
    time_limit_s: int = 60,
    verbose: bool = True,
) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """
    Assign all intra-poule round-robin matches to (slot, terrain) pairs using CP-SAT.
    All poules share the same terrain slots (they compete for the same venue).

    Parameters
    -----------
    poules          {poule_name: [team, …]} — teams grouped by poule.
    team_avail      {team_name: {slot_label, …}} — availability per team.
    terrain_slots   List of slot dicts from generate_terrain_slots / load_terrain_slots.
    time_limit_s    Maximum solver wall-clock time in seconds.
    verbose         Print a summary after solving.

    Returns
    --------
    (scheduled, unscheduled)
      scheduled   — list of {"poule": "A", "match": (A, B), "slot": "…", "terrain": "T1"}
      unscheduled — list of (poule, A, B) tuples that could not be placed
    """
    # Build flat match list with poule tag (only intra-poule round-robin)
    matches: list[tuple[str, str, str]] = [
        (poule, ta, tb)
        for poule, teams in poules.items()
        for ta, tb in combinations(teams, 2)
    ]
    all_teams = [t for ts in poules.values() for t in ts]

    # De-duplicate slot labels while preserving order
    slot_labels: list[str] = list(dict.fromkeys(s["slot"] for s in terrain_slots))
    date_of_slot: dict[str, str] = {s["slot"]: s["date"] for s in terrain_slots}
    # All actual (slot, terrain) pairs that the venue provides
    st_pairs: list[tuple[str, str]] = [(s["slot"], s["terrain"]) for s in terrain_slots]

    model = cp_model.CpModel()

    # ── Decision variables ────────────────────────────────────────────────────
    # x[(match_idx, st_idx)] = 1  iff  match is played at that (slot, terrain)
    # Variables are only created when both teams are available — prunes the model.
    x: dict[tuple[int, int], cp_model.IntVar] = {}

    for m_idx, (_, ta, tb) in enumerate(matches):
        avail_a = team_avail.get(ta, set())
        avail_b = team_avail.get(tb, set())
        for st_idx, (slot, _terrain) in enumerate(st_pairs):
            if slot in avail_a and slot in avail_b:
                x[(m_idx, st_idx)] = model.new_bool_var(f"x_m{m_idx}_st{st_idx}")

    # ── Constraints ───────────────────────────────────────────────────────────

    # 1. Each match is played at most once
    for m_idx in range(len(matches)):
        match_vars = [x[(m_idx, st)] for st in range(len(st_pairs)) if (m_idx, st) in x]
        if match_vars:
            model.add(sum(match_vars) <= 1)

    # 2. Each (slot, terrain) pair hosts at most one match
    for st_idx in range(len(st_pairs)):
        slot_vars = [x[(m, st_idx)] for m in range(len(matches)) if (m, st_idx) in x]
        if slot_vars:
            model.add(sum(slot_vars) <= 1)

    # 3. Each team plays at most one match per calendar day
    all_dates = list(dict.fromkeys(s["date"] for s in terrain_slots))
    for team in all_teams:
        for date in all_dates:
            st_on_date = [
                st_idx
                for st_idx, (slot, _) in enumerate(st_pairs)
                if date_of_slot[slot] == date
            ]
            team_day_vars = [
                x[(m_idx, st_idx)]
                for m_idx, (_, ta, tb) in enumerate(matches)
                if ta == team or tb == team
                for st_idx in st_on_date
                if (m_idx, st_idx) in x
            ]
            if team_day_vars:
                model.add(sum(team_day_vars) <= 1)

    # ── Objective: schedule as many matches as possible ───────────────────────
    model.maximize(sum(x.values()))

    # ── Solve ─────────────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.log_search_progress = False
    status = solver.solve(model)

    scheduled: list[dict] = []
    scheduled_matches: set[int] = set()

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for m_idx, (poule, ta, tb) in enumerate(matches):
            for st_idx, (slot, terrain) in enumerate(st_pairs):
                if (m_idx, st_idx) in x and solver.value(x[(m_idx, st_idx)]):
                    scheduled.append(
                        {"poule": poule, "match": (ta, tb), "slot": slot, "terrain": terrain}
                    )
                    scheduled_matches.add(m_idx)
                    break

    unscheduled = [
        (poule, ta, tb)
        for i, (poule, ta, tb) in enumerate(matches)
        if i not in scheduled_matches
    ]

    if verbose:
        status_name = solver.status_name(status)
        total = len(matches)
        n_sch = len(scheduled)
        n_slots = len(slot_labels)
        n_slot_terrain = len(st_pairs)
        print(f"\n{'='*60}")
        print(f"  Poules:         {len(poules)}")
        print(f"  Total matches:  {total}")
        print(f"  Scheduled:      {n_sch}  ({100*n_sch/total:.0f}%)")
        print(f"  Unscheduled:    {len(unscheduled)}")
        print(f"  Venue slots:    {n_slot_terrain}  ({n_slots} time slots x terrains)")
        print(f"  Solver status:  {status_name}")
        for poule_name, teams in poules.items():
            p_total = len(list(combinations(teams, 2)))
            p_sch   = sum(1 for s in scheduled if s["poule"] == poule_name)
            print(f"  Poule {poule_name:6s}:   {p_sch}/{p_total} matches  ({', '.join(teams)})")
        print(f"{'='*60}\n")

        if unscheduled:
            print("Unscheduled matches (no common availability):")
            for poule, ta, tb in unscheduled:
                print(f"  [{poule}]  {ta}  vs  {tb}")
            print()

    return scheduled, unscheduled


# ── Output helpers ─────────────────────────────────────────────────────────────

def to_dataframes(
    scheduled: list[dict],
    unscheduled: list[tuple[str, str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convert results to sorted DataFrames."""
    if scheduled:
        df_sched = pd.DataFrame(
            [
                {
                    "Poule": s["poule"],
                    "Date": s["slot"].split()[0],
                    "Time": s["slot"].split()[1],
                    "Terrain": s["terrain"],
                    "Team A": s["match"][0],
                    "Team B": s["match"][1],
                }
                for s in scheduled
            ]
        ).sort_values(["Poule", "Date", "Time", "Terrain"]).reset_index(drop=True)
    else:
        df_sched = pd.DataFrame(columns=["Poule", "Date", "Time", "Terrain", "Team A", "Team B"])

    df_unsched = (
        pd.DataFrame([{"Poule": p, "Team A": a, "Team B": b} for p, a, b in unscheduled])
        if unscheduled
        else pd.DataFrame(columns=["Poule", "Team A", "Team B"])
    )

    return df_sched, df_unsched


def export_schedule_overview_pdf(
    df_sched: pd.DataFrame,
    path: str,
    club_name: str = "Tennis Club",
    season: str = "",
) -> None:
    """
    Generate a compact planning overview PDF:
    all matches from all poules combined, sorted by date then time,
    displayed in a single chronological table.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError:
        print("reportlab not installed — skipping overview PDF.  pip install reportlab")
        return

    if df_sched.empty:
        print("No schedule data — skipping overview PDF.")
        return

    PAGE_W, PAGE_H = A4
    MARGIN = 2 * cm

    CLAY        = colors.HexColor("#C1440E")
    CLAY_LIGHT  = colors.HexColor("#F2E0D0")
    DARK        = colors.HexColor("#1C1C1C")
    MID_GREY    = colors.HexColor("#6D6D6D")
    WHITE       = colors.white
    DAY_BG      = colors.HexColor("#F7F0EC")   # subtle warm tint for date group headers

    styles = getSampleStyleSheet()

    S_TITLE = ParagraphStyle(
        "Title2", parent=styles["Title"],
        fontSize=26, textColor=CLAY, spaceAfter=4,
        fontName="Helvetica-Bold", alignment=TA_CENTER,
    )
    S_SUBTITLE = ParagraphStyle(
        "Subtitle2", parent=styles["Normal"],
        fontSize=12, textColor=MID_GREY, spaceAfter=2,
        fontName="Helvetica", alignment=TA_CENTER,
    )

    # Sort all matches by date then time
    df_sorted = df_sched.sort_values(["Date", "Time", "Terrain"]).reset_index(drop=True)

    # Decide columns: include Poule only if multiple poules exist
    has_poule = "Poule" in df_sorted.columns and df_sorted["Poule"].nunique() > 1

    # Column widths
    if has_poule:
        col_hdrs = ["Date", "Time", "Terrain", "Poule", "Team A", "vs", "Team B"]
        date_w    = 2.4 * cm
        time_w    = 1.6 * cm
        terr_w    = 1.6 * cm
        poule_w   = 1.5 * cm
        vs_w      = 0.7 * cm
        team_w    = (PAGE_W - 2 * MARGIN - date_w - time_w - terr_w - poule_w - vs_w) / 2
        col_widths = [date_w, time_w, terr_w, poule_w, team_w, vs_w, team_w]
    else:
        col_hdrs = ["Date", "Time", "Terrain", "Team A", "vs", "Team B"]
        date_w    = 2.6 * cm
        time_w    = 1.8 * cm
        terr_w    = 1.8 * cm
        vs_w      = 0.8 * cm
        team_w    = (PAGE_W - 2 * MARGIN - date_w - time_w - terr_w - vs_w) / 2
        col_widths = [date_w, time_w, terr_w, team_w, vs_w, team_w]

    # Build table rows, inserting a shaded date-group separator row on date change
    table_data = [col_hdrs]
    row_styles = []   # extra TableStyle commands collected per row
    current_date = None
    data_row_idx = 1  # index 0 = header

    for _, row in df_sorted.iterrows():
        date = row["Date"]
        if date != current_date:
            current_date = date
            # Date group header row (spans all columns)
            span_row = [date] + [""] * (len(col_hdrs) - 1)
            table_data.append(span_row)
            row_styles.append(
                ("SPAN",        (0, data_row_idx), (-1, data_row_idx))
            )
            row_styles.append(
                ("BACKGROUND",  (0, data_row_idx), (-1, data_row_idx), DAY_BG)
            )
            row_styles.append(
                ("FONTNAME",    (0, data_row_idx), (-1, data_row_idx), "Helvetica-Bold")
            )
            row_styles.append(
                ("FONTSIZE",    (0, data_row_idx), (-1, data_row_idx), 9)
            )
            row_styles.append(
                ("TEXTCOLOR",   (0, data_row_idx), (-1, data_row_idx), DARK)
            )
            data_row_idx += 1

        if has_poule:
            table_data.append([
                "",  # date already shown in group header
                row["Time"], row["Terrain"], row.get("Poule", ""),
                row["Team A"], "vs", row["Team B"],
            ])
        else:
            table_data.append([
                "", row["Time"], row["Terrain"],
                row["Team A"], "vs", row["Team B"],
            ])
        data_row_idx += 1

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    base_style = [
        # Header row
        ("BACKGROUND",  (0, 0), (-1, 0),  CLAY),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  9),
        # Body
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 8),
        ("TEXTCOLOR",   (0, 1), (-1, -1), DARK),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CLAY_LIGHT]),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ] + row_styles
    t.setStyle(TableStyle(base_style))

    story = []
    story.append(Spacer(1, 1.2 * cm))
    story.append(Paragraph(club_name, S_TITLE))
    if season:
        story.append(Paragraph(season, S_SUBTITLE))
    story.append(Paragraph("Full Planning Overview", S_SUBTITLE))
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=CLAY))
    story.append(Spacer(1, 0.6 * cm))
    story.append(t)

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"{club_name} — Full Planning Overview",
        author=club_name,
    )
    doc.build(story)
    print(f"Saved overview PDF to: {path}")


def export_pdf(
    df_sched: pd.DataFrame,
    team_info_df: pd.DataFrame | None,
    path: str,
    club_name: str = "Tennis Club",
    season: str = "",
) -> None:
    """
    Generate a tennis-club-style PDF with:
      - Cover header (club name, season)
      - Per-poule team sheet: team name, players, rankings, phone numbers
      - Per-team match schedule table
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
            TableStyle,
        )
    except ImportError:
        print("reportlab not installed — skipping PDF.  pip install reportlab")
        return

    PAGE_W, PAGE_H = A4
    MARGIN = 2 * cm

    # ── Colour palette (tennis / clay) ────────────────────────────────────────
    CLAY      = colors.HexColor("#C1440E")   # terracotta / header
    CLAY_LIGHT= colors.HexColor("#F2E0D0")   # soft peach for alt rows
    DARK      = colors.HexColor("#1C1C1C")
    MID_GREY  = colors.HexColor("#6D6D6D")
    WHITE     = colors.white
    GREEN_COURT = colors.HexColor("#2D6A4F") # dark green accent

    styles = getSampleStyleSheet()

    S_TITLE = ParagraphStyle(
        "ClubTitle",
        parent=styles["Title"],
        fontSize=28,
        textColor=CLAY,
        spaceAfter=4,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    S_SEASON = ParagraphStyle(
        "Season",
        parent=styles["Normal"],
        fontSize=13,
        textColor=MID_GREY,
        spaceAfter=2,
        fontName="Helvetica",
        alignment=TA_CENTER,
    )
    S_POULE_HDR = ParagraphStyle(
        "PouleHeader",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=WHITE,
        backColor=CLAY,
        spaceAfter=6,
        spaceBefore=14,
        fontName="Helvetica-Bold",
        leftIndent=-MARGIN + 2 * cm,
        rightIndent=-MARGIN + 2 * cm,
        borderPad=6,
        alignment=TA_LEFT,
    )
    S_SECTION = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=GREEN_COURT,
        spaceBefore=10,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    S_BODY = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        textColor=DARK,
        fontName="Helvetica",
    )

    def _team_table(rows, col_headers):
        col_count = len(col_headers)
        col_w = (PAGE_W - 2 * MARGIN) / col_count
        data = [col_headers] + rows
        t = Table(data, colWidths=[col_w] * col_count, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0),  CLAY),
            ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
            ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, 0),  9),
            ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CLAY_LIGHT]),
            ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",    (0, 1), (-1, -1), 8),
            ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("TOPPADDING",  (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    def _schedule_table(rows, col_headers):
        # Measure the widest content in the "Round" column (index 3) and
        # "Opponent" column (index 4) to size them proportionally.
        # Columns: Date(0), Time(1), Terrain(2), Round(3), Opponent(4)
        from reportlab.pdfbase.pdfmetrics import stringWidth
        FONT_BODY, FONT_SIZE_BODY = "Helvetica", 8
        FONT_HDR,  FONT_SIZE_HDR  = "Helvetica-Bold", 9
        PADDING = 0.3 * cm  # horizontal padding per cell (each side)

        def _col_min_width(col_idx):
            all_vals = [col_headers[col_idx]] + [r[col_idx] for r in rows if r[col_idx]]
            return max(
                stringWidth(str(v),
                            FONT_HDR  if i == 0 else FONT_BODY,
                            FONT_SIZE_HDR if i == 0 else FONT_SIZE_BODY)
                for i, v in enumerate(all_vals)
            ) + 2 * PADDING

        date_w  = 2.2 * cm
        time_w  = 1.6 * cm
        terr_w  = 1.6 * cm
        round_w = max(_col_min_width(3), 2.5 * cm)
        opp_w   = max(_col_min_width(4), 2.5 * cm)
        # If everything fits, honour natural widths; otherwise fill the page.
        available = PAGE_W - 2 * MARGIN
        fixed     = date_w + time_w + terr_w
        used      = round_w + opp_w
        if fixed + used <= available:
            # Distribute any leftover space equally to round/opponent columns
            extra = (available - fixed - used) / 2
            round_w += extra
            opp_w   += extra
        else:
            # Scale round/opponent proportionally to fill available width
            scale  = (available - fixed) / used
            round_w *= scale
            opp_w   *= scale

        widths = [date_w, time_w, terr_w, round_w, opp_w]
        data = [col_headers] + rows
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0),  GREEN_COURT),
            ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
            ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, 0),  9),
            ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CLAY_LIGHT]),
            ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",    (0, 1), (-1, -1), 8),
            ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("TOPPADDING",  (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    # ── Build story ───────────────────────────────────────────────────────────
    story = []

    # Cover header
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(club_name, S_TITLE))
    if season:
        story.append(Paragraph(season, S_SEASON))
    story.append(Paragraph("Competition Schedule", S_SEASON))
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=CLAY))
    story.append(Spacer(1, 0.8 * cm))

    # Determine poules to render
    if df_sched.empty and (team_info_df is None or team_info_df.empty):
        story.append(Paragraph("No schedule data available.", S_BODY))
    else:
        poule_names = sorted(
            df_sched["Poule"].unique().tolist() if not df_sched.empty else []
        )
        if team_info_df is not None and "Poule" in team_info_df.columns:
            poule_names = sorted(set(poule_names) | set(team_info_df["Poule"].unique()))

        for p_idx, poule in enumerate(poule_names):
            if p_idx > 0:
                story.append(PageBreak())

            story.append(Paragraph(f"  Poule {poule}", S_POULE_HDR))
            story.append(Spacer(1, 0.4 * cm))

            # ── Team info block ──────────────────────────────────────────────
            if team_info_df is not None and not team_info_df.empty:
                p_teams = team_info_df[team_info_df["Poule"] == poule] if "Poule" in team_info_df.columns else team_info_df

                # Determine which detail columns are present
                detail_cols = [c for c in ["Player 1", "Player 2", "Tel P1", "Tel P2"]
                               if c in p_teams.columns]
                team_hdrs = ["Team"] + detail_cols

                team_rows = []
                for _, row in p_teams.iterrows():
                    team_rows.append([row.get("Team", "")] + [row.get(c, "") for c in detail_cols])

                if team_rows:
                    story.append(Paragraph("Teams & Players", S_SECTION))
                    story.append(_team_table(team_rows, team_hdrs))
                    story.append(Spacer(1, 0.6 * cm))

            # ── Schedule per team ────────────────────────────────────────────
            if not df_sched.empty:
                p_sched = df_sched[df_sched["Poule"] == poule]
                all_teams_in_poule = sorted(
                    set(p_sched["Team A"].tolist() + p_sched["Team B"].tolist())
                )

                story.append(Paragraph("Match Schedule", S_SECTION))
                story.append(Spacer(1, 0.2 * cm))

                sched_hdrs = ["Date", "Time", "Terrain", "Team", "Opponent"]
                sched_rows = []
                for team in all_teams_in_poule:
                    mask = (p_sched["Team A"] == team) | (p_sched["Team B"] == team)
                    team_matches = p_sched[mask].sort_values(["Date", "Time"])
                    for rn, (_, row) in enumerate(team_matches.iterrows(), 1):
                        opp = row["Team B"] if row["Team A"] == team else row["Team A"]
                        sched_rows.append([
                            row["Date"], row["Time"], row["Terrain"],
                            team, opp,
                        ])
                    if len(team_matches) > 0:
                        sched_rows.append(["", "", "", "", ""])  # blank separator row

                if sched_rows:
                    story.append(_schedule_table(sched_rows, sched_hdrs))

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"{club_name} — Competition Schedule",
        author=club_name,
    )
    doc.build(story)
    print(f"Saved PDF to:      {path}")


def print_schedule(df_sched: pd.DataFrame) -> None:
    """Pretty-print the schedule grouped by poule and date."""
    if df_sched.empty:
        print("No matches scheduled.")
        return
    has_poule = "Poule" in df_sched.columns and df_sched["Poule"].nunique() > 1
    poule_groups = df_sched.groupby("Poule") if has_poule else [(None, df_sched)]
    for poule_name, poule_df in poule_groups:
        if has_poule:
            print(f"\n══ Poule {poule_name} ════════════════════════════════════")
        for date, group in poule_df.groupby("Date"):
            print(f"── {date} ────────────────────────────────────")
            for _, row in group.iterrows():
                print(f"  {row['Time']}  [{row['Terrain']}]  {row['Team A']}  vs  {row['Team B']}")
    print()


def export_excel(
    df_sched: pd.DataFrame,
    df_unsched: pd.DataFrame,
    path: str,
    team_info_df: pd.DataFrame | None = None,
) -> None:
    """
    Export schedule to a colour-coded Excel workbook.

    Sheets
    -------
    - "Teams"        — team / player info (only when team_info_df is provided)
    - "Schedule"     — full schedule sorted by date / time / terrain
    - "By Team"      — per-team match list
    - "Poule X"      — one sheet per poule (when multiple poules exist)
    - "Unscheduled"  — matches that could not be placed (if any)
    """
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils.dataframe import dataframe_to_rows
    except ImportError:
        print("openpyxl not installed — saving as CSV instead.  pip install openpyxl")
        df_sched.to_csv(path.replace(".xlsx", "_schedule.csv"), index=False)
        return

    BLUE_HEADER  = PatternFill("solid", fgColor="2E75B6")
    GREEN_HEADER = PatternFill("solid", fgColor="375623")
    RED_HEADER   = PatternFill("solid", fgColor="C00000")
    ALT_ROW      = PatternFill("solid", fgColor="DEEAF1")
    WHITE_FONT   = Font(color="FFFFFF", bold=True)

    def _write_sheet(ws, df: pd.DataFrame, header_fill, col_widths=None):
        for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
            for c_idx, val in enumerate(row, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if r_idx == 1:
                    cell.fill = header_fill
                    cell.font = WHITE_FONT
                elif r_idx % 2 == 0:
                    cell.fill = ALT_ROW
        ws.row_dimensions[1].height = 20
        for col in ws.columns:
            wanted = max((len(str(c.value or "")) for c in col), default=8) + 4
            ws.column_dimensions[col[0].column_letter].width = min(wanted, 30)

    wb = openpyxl.Workbook()

    # Sheet 1: team / player info (if available)
    ws_first = wb.active
    if team_info_df is not None and not team_info_df.empty:
        ws_first.title = "Teams"
        _write_sheet(ws_first, team_info_df, GREEN_HEADER)
        ws1 = wb.create_sheet("Schedule")
    else:
        ws_first.title = "Schedule"
        ws1 = ws_first

    # Schedule sheet
    _write_sheet(ws1, df_sched, BLUE_HEADER)

    # Sheet 2: per-team view
    if not df_sched.empty:
        by_team_rows = []
        all_teams = sorted(
            set(df_sched["Team A"].tolist() + df_sched["Team B"].tolist())
        )
        for team in all_teams:
            mask = (df_sched["Team A"] == team) | (df_sched["Team B"] == team)
            for _, row in df_sched[mask].iterrows():
                opponent = row["Team B"] if row["Team A"] == team else row["Team A"]
                by_team_rows.append(
                    {
                        "Poule": row.get("Poule", ""),
                        "Team": team,
                        "Date": row["Date"],
                        "Time": row["Time"],
                        "Terrain": row["Terrain"],
                        "Opponent": opponent,
                    }
                )
        df_by_team = pd.DataFrame(by_team_rows).sort_values(["Poule", "Team", "Date", "Time"])
        ws2 = wb.create_sheet("By Team")
        _write_sheet(ws2, df_by_team, BLUE_HEADER)

    # Sheet 3: one sheet per poule (if multiple poules)
    if not df_sched.empty and "Poule" in df_sched.columns and df_sched["Poule"].nunique() > 1:
        for poule_name in sorted(df_sched["Poule"].unique()):
            df_p = df_sched[df_sched["Poule"] == poule_name].reset_index(drop=True)
            ws_p = wb.create_sheet(f"Poule {poule_name}")
            _write_sheet(ws_p, df_p, BLUE_HEADER)

    # Sheet 4: unscheduled (optional)
    if not df_unsched.empty:
        ws3 = wb.create_sheet("Unscheduled")
        _write_sheet(ws3, df_unsched, RED_HEADER)

    wb.save(path)
    print(f"Saved schedule to: {path}")


# ── Static HTML export (GitHub Pages) ─────────────────────────────────────────

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
const SPONSORS = [
  { img: 'images/sponsors/s30.png',              url: 'https://www.facebook.com/Bart-Van-Den-Bosch-953637634704875/',  name: 'Bart Van Den Bosch' },
  { img: 'images/sponsors/s08.png',              url: 'https://ensys.be/',                                             name: 'Ensys' },
  { img: 'images/sponsors/bdvwindows.png',       url: 'https://bdvwindows.be/',                                        name: 'BDV Windows' },
  { img: 'images/sponsors/s02.png',              url: 'https://www.vennincx.be/',                                      name: 'Vennincx' },
  { img: 'images/sponsors/s05.png',              url: 'https://delhaizeputtekapellen.be/',                             name: 'Delhaize Putte-Kapellen' },
  { img: 'images/sponsors/s09.png',              url: 'https://www.auctionport.be/',                                   name: 'AuctionPort' },
  { img: 'images/sponsors/s12.png',              url: 'https://www.corpusfit.be/',                                     name: 'CorpusFit' },
  { img: 'images/sponsors/s20.png',              url: 'https://www.facebook.com/MoniqueStamByEva/',                   name: 'Monique Stam By Eva' },
  { img: 'images/sponsors/s22.png',              url: 'https://www.concreetbv.be/',                                   name: 'Concreet BV' },
  { img: 'images/sponsors/s24.png',              url: 'https://bobjanssens.com/',                                     name: 'Bob Janssens' },
  { img: 'images/sponsors/s26.png',              url: 'https://www.deveehoeve.be/',                                   name: 'De Veehoeve' },
  { img: 'images/sponsors/s28.png',              url: 'https://www.groepvanheyst.be/',                                name: 'Groep Van Heyst' },
  { img: 'images/sponsors/direggio.png',         url: 'https://www.direggio.co/',                                     name: 'DiReggio' },
  { img: 'images/sponsors/s31.png',              url: 'https://koosi.be/',                                            name: 'Koosi' },
  { img: 'images/sponsors/s32.png',              url: 'https://www.renovant.be/',                                     name: 'Renovant' },
  { img: 'images/sponsors/s35.png',              url: 'https://www.meesters.be/',                                     name: 'Meesters Acccountants' },
  { img: 'images/sponsors/s36.png',              url: 'https://www.stabilos.be/',                                     name: 'Stabilos' },
  { img: 'images/sponsors/s37.png',              url: 'https://steenhouwerij-denisse.be/',                            name: 'Steenhouwerij Denisse' },
  { img: 'images/sponsors/s38.png',              url: null,                                                           name: 'APPPS Group' },
  { img: 'images/sponsors/s39.png',              url: 'https://www.brasserie-tkoetshuis.be/home/',                   name: '\'t Koetshuis' },
  { img: 'images/sponsors/bestratingen_mees.png',url: 'https://www.bestratingenmees.be/',                             name: 'Bestratingen Mees' },
];
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
    '<p style="font-size:1.05rem;line-height:1.8;margin-bottom:14px">' +
        '\u2026 een club <strong>voor iedereen</strong>. Of je nu net begint, al jaren speelt of gewoon graag een balletje slaat \u2014 bij TC Kooike voel je je meteen thuis. ' +
        'Onze club telt leden van alle leeftijden en niveaus, verenigd door \u00e9\u00e9n passie: de liefde voor tennis.</p>' +
        '<p style="font-size:1.05rem;line-height:1.8;margin-bottom:14px">' +
        '\u2026 een club waar <strong>tennisplezier heerst</strong>. Van ontspannen dubbels op zondagochtend tot spannende competitiematchen \u2014 de glimlach op de baan is altijd het grootste. ' +
        'Naast het tennis zorgen we ook voor gezelligheid buiten de lijnen: clubactiviteiten, tornooien en een warm clubgevoel het hele jaar door.</p>' +
        '<p style="font-size:1.05rem;line-height:1.8;margin-bottom:14px">' +
        '\u2026 een club <strong>van winnaars</strong>. Onze leden schitteren seizoen na seizoen in de interclub \u2014 maar winnen staat bij ons nooit boven het plezier. ' +
        'Wie wil groeien, vindt bij ons de perfecte omgeving: professionele tennislessen via WhackIt, laddercompetitie voor extra uitdaging en ervaren medespelers die je graag verder helpen.</p>' +
        '<p style="font-size:1.05rem;line-height:1.8">' +
        '\u2026 maar bovenal een club met een heel groot <strong>\u2764\ufe0f</strong>. TC Kooike is meer dan een tennisclub \u2014 het is een gemeenschap. ' +
        'Een plek waar vriendschappen worden gesmeed, herinneringen worden gemaakt en iedereen altijd welkom is.</p>' +
    '</div></div>' +
    '<div class="welkom-bottom-grid" style="display:grid;grid-template-columns:2fr 1fr;gap:16px;align-items:stretch">' +
    '<div class="card" style="margin-bottom:0"><div class="card-head">🎾 Hoe reserveren?</div><div class="card-body">' +
    '<p style="font-size:.92rem;line-height:1.8;margin-bottom:10px">' +
    'TC Kooike is gevestigd in <strong>Kapellen</strong>, met meerdere buitenterreinen en padelvelden. ' +
    'Terreinreservaties verlopen eenvoudig via Tennis &amp; Padel Vlaanderen.</p>' +
    '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:14px">' +
    '<a href="https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/reserveer-een-terrein?clubId=2158" target="_blank" class="cta-btn">🎾 Reserveer een terrein</a>' +
    '<a href="https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/lid-worden?clubId=2158" target="_blank" class="cta-btn">✅ Word lid</a>' +
    '</div>' +
    '</div></div>' +
    '<div class="card" style="margin-bottom:0;overflow:hidden;display:flex;flex-direction:column"><div class="card-head">🤝 Sponsors</div><div class="card-body" style="padding:12px;flex:1;display:flex;align-items:stretch">' +
    (function() {
      const shuffled = [...SPONSORS].sort(() => Math.random() - 0.5);
      const track = shuffled.map(s => '<img src="' + s.img + '" alt="' + s.name + '" title="' + s.name + '" onerror="this.style.display=\'none\'">' ).join('');
      return '<div class="marquee-wrap"><div class="marquee-track">' + track + track + '</div></div>';
    })() +
    '</div></div>' +
    '</div>';
}

function panelKalender() {
  const events = [
    { date: '8 februari 2026',       desc: 'Deadline korting lidmaatschap',    note: 'Schrijf vroeg in voor een korting op het lidgeld' },
    { date: 'Maart 2026',            desc: 'Heraanleg velden',                 note: null },
    { date: '6 april 2026',           desc: 'Start seizoen 🎉',                 note: 'Terreinreservaties via Tennis & Padel Vlaanderen' },
    { date: '1 mei 2026',            desc: 'Dubbel gemengd dag 👫',            note: '<a href="https://docs.google.com/forms/d/e/1FAIpQLSd_iqhaNux1ese4GDZVSK1xMDTH_Ppv1lXLDc6u-yKT24G_2A/viewform?usp=publish-editor" target="_blank">Schrijf je nu hier in!</a>' },
    { date: '12 – 21 juni 2026',     desc: 'Bring a Smile – Tornooi',         note: null },
    { date: '28 augustus 2026',      desc: 'Nacht der Dubbels 🌙',             note: null },
    { date: '5 – 20 september 2026', desc: 'Fairplay Tornooi',                note:  null },
  ];
  const rows = events.map(e =>
    '<div class="kal-item"><div class="kal-date">' + esc(e.date) + '</div>' +
    '<div class="kal-desc">' + esc(e.desc) + (e.note ? '<small>' + e.note + '</small>' : '') + '</div></div>'
  ).join('');
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

  const rows = filtered.map(({ m, dt }) => {
    const prefix = weekdayNl[dt.getDay()] || '';
    const shownDate = (prefix ? prefix + ' ' : '') + String(m.datum || '');
    return '<tr>' +
      '<td>' + esc(shownDate) + '</td>' +
      '<td>' + esc(m.reeks || '') + '</td>' +
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

  return '<div class="card"><div class="card-head">🎾 Interclub 2026</div><div class="card-body">' +
    '<div class="tbl-wrap"><table>' +
    '<thead><tr><th>Datum</th><th>Reeks</th><th>Kapitein</th><th>Ontvangende club</th><th>Bezoekende club</th></tr></thead>' +
    '<tbody>' + rows + '</tbody>' +
    '</table></div>' +
    '</div></div>';
}

function panelBestuur() {
  const board = [
    { name: 'Timothy Van Daele',    role: 'Voorzitter & elit verantwoordelijke',                    img: 'images/bestuur/timothy.jpg' },
    { name: 'Anouk Van den Branden',role: 'Secretaris, elit verantwoordelijke & tennisschool',      img: 'images/bestuur/anouk.jpg' },
    { name: 'Philip Somers',        role: 'Penningmeester & aanspreekpunt padel',                   img: 'images/bestuur/philip.jpg' },
    { name: 'Jan Viroux',           role: 'Bestuurslid, tennisschool & aanspreekpunt padel',        img: 'images/bestuur/jan.jpg' },
    { name: 'Steven De Cuyper',     role: 'Sponsoring, beheer & organisatie events',                img: 'images/bestuur/steven.jpg' },
    { name: 'Glen Van Dyck',        role: 'Bestuurslid, beheer & organisatie events',               img: 'images/bestuur/glen.jpg' },
  ];
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
      '<p style="font-size:.8rem;color:var(--text-muted);margin-bottom:14px">Alle leden van TC Kooike verklaren kennis te hebben genomen van het clubreglement en verplichten zich dit na te leven.</p>' +

      '<p style="font-weight:700;color:var(--clay-dark);margin:14px 0 4px">LIDMAATSCHAP</p>' +
      '<p>Leden kunnen hun lidmaatschap jaarlijks verlengen via de website van Tennis Vlaanderen. De inschrijving is pas definitief zodra de betaling volledig is verwerkt en goedgekeurd door de club.</p>' +
      '<p style="margin-top:6px">De actuele bedragen voor de lidgelden en eventuele kortingen worden aan het begin van het seizoen aan de leden verstrekt en zijn tevens te raadplegen op de websites van de club en Tennis Vlaanderen. Het dagelijks bestuur behoudt zich het recht voor om de lidgelden jaarlijks aan te passen; dit wordt gepresenteerd op het infomoment in november.</p>' +
      '<p style="margin-top:6px">Nieuwe leden kunnen zich inschrijven via Tennis Vlaanderen onder de tab &lsquo;Tarieven&rsquo;. De verwerkingstijd bedraagt circa 5 werkdagen.</p>' +

      '<p style="font-weight:700;color:var(--clay-dark);margin:14px 0 4px">TERREINEN</p>' +
      '<p>De club beschikt over vier tennisterreinen met gravelondergrond, toegankelijk van april tot oktober. Het gebruik is, na reservering, voorbehouden aan spelende leden (betaald lidmaatschap) en gastspelers (€&nbsp;5,00/speler/uur of €&nbsp;15 per terrein).</p>' +
      '<p style="margin-top:6px">Bij overvloedige regenval is spelen niet toegestaan ter bescherming van de ondergrond. Het bestuur kan terreinen preventief sluiten en reservaties annuleren. De terreinen mogen uitsluitend betreden worden met gepaste schoenen.</p>' +

      '<p style="font-weight:700;color:var(--clay-dark);margin:14px 0 4px">RESERVATIES</p>' +
      '<p>Reservatiezones: Terrein 1, 2 &amp; 3 &mdash; 90 minuten &bull; Terrein 4 &mdash; 60 minuten.</p>' +
      '<p style="margin-top:6px">Na elk speelmoment dient het terrein geveegd en (indien nodig) besproeid te worden. Afval hoort in de vuilnisbakken.</p>' +
      '<p style="margin-top:6px">In de <strong>avondzone</strong> is 1 reservatie per 7 dagen toegestaan; in de <strong>dagzone</strong> 2 reservaties per 7 dagen (onafhankelijk van elkaar). Jeugdleden (&lt;&nbsp;18 jaar) kunnen enkel op de dag zelf (8 uur van tevoren) een terrein in de avondzone reserveren.</p>' +
      '<p style="margin-top:6px">Het bestuur behoudt zich het recht voor om terreinen te reserveren. Voorrang op vrije reservaties hebben: competitie-ontmoetingen (Interclub, ART, Noorderkempen, Beker Claus), tornooien, tennislessen, clubdagen/-activiteiten en onderhoud.</p>' +

      '<p style="font-weight:700;color:var(--clay-dark);margin:14px 0 4px">GASTSPELER(S)</p>' +
      '<p>Een gastspeler betaalt vooraf €&nbsp;5,00 per persoon of €&nbsp;15 per terrein via het automatische betaalsysteem gekoppeld aan de reservatie.</p>' +

      '<p style="font-weight:700;color:var(--clay-dark);margin:14px 0 4px">ACCOMMODATIE &amp; KLEEDKAMERS</p>' +
      '<p>Bij beschadiging of defecten aan de accommodatie (netten, veegmatten, sproeisysteem, verlichting) dient dit zo spoedig mogelijk gemeld te worden aan een bestuurslid of de terreinverantwoordelijke. Elk lid is verantwoordelijk voor schade die hij/zij veroorzaakt.</p>' +
      '<p style="margin-top:6px">Zorg ervoor dat douches en kleedkamers netjes worden achtergelaten. De club is niet verantwoordelijk voor diefstal van persoonlijke spullen. Gelieve elke overtreding onmiddellijk aan een bestuurslid te melden. Tijdens sluitingstijden of privé-feesten van Bar Castel dient u de achteringang te gebruiken.</p>' +

      '<p style="font-weight:700;color:var(--clay-dark);margin:14px 0 4px">TENNISLESSEN</p>' +
      '<p>In samenwerking met tennisschool WhackIt organiseert de club tennislessen vanaf april. Lesnemers zijn verplicht lid van de club. Betaling van lid- en lesgeld dient voor aanvang van de lessenreeks in orde te zijn; bij ontbreken van betaling wordt toegang tot de tennisvelden geweigerd. Tarieven zijn te raadplegen op <a href="https://www.tckooike.com" target="_blank">www.tckooike.com</a> of via Tennis Vlaanderen.</p>' +
      '<p style="margin-top:6px">Het organiseren van tennislessen met andere tennisleraren is toegestaan mits toestemming van het dagelijks bestuur.</p>' +

      '<p style="font-weight:700;color:var(--clay-dark);margin:14px 0 4px">SPORTONGEVAL</p>' +
      '<p>Als lid van Tennis &amp; Padel Vlaanderen bent u via de vereniging verzekerd tegen sportongevallen. De aangifte van het sportongeval wordt door de club in behandeling genomen. Bij een sportongeval dient u zo snel mogelijk (binnen 14 dagen) contact op te nemen via <a href="mailto:tckooike@gmail.com">tckooike@gmail.com</a> en de volgende gegevens te verstrekken:</p>' +
      '<ul style="margin:8px 0 0 18px;line-height:2">' +
        '<li>Foto identiteitskaart</li>' +
        '<li>Woonadres</li>' +
        '<li>Contactgegevens</li>' +
        '<li>Aansluiting bij ziekenfonds</li>' +
        '<li>Rekeningnummer bank</li>' +
        '<li>Documenten van de huisarts of ziekenhuis</li>' +
        '<li>Gedetailleerde omschrijving van het ongeval</li>' +
      '</ul>' +

      '<p style="font-weight:700;color:var(--clay-dark);margin:14px 0 4px">NIET-NALEVING REGLEMENT</p>' +
      '<p>Leden die één of meerdere bepalingen van dit reglement niet naleven, kunnen door bestuursleden de toegang tot de terreinen ontzegd worden. Het bestuur kan één of meerdere maatregelen opleggen, wat kan leiden tot uitsluiting van de club en/of weigering van het lidmaatschap voor het volgende jaar.</p>' +

      '</div></div>';
}

function panelSfeer() {
  const sfeerImgs = [
    { f: 'sfeer1',     c: 'Sfeerbeelden' }, { f: 'sfeer2',    c: '' }, { f: 'sfeer3', c: '' },
    { f: 'sfeer4',     c: '' },             { f: 'sfeer5',    c: '' }, { f: 'sfeer6', c: '' },
    { f: 'sfeer7',     c: '' },             { f: 'sfeer8',    c: '' },
    { f: 'kids1',      c: 'Kids & jeugd' }, { f: 'kids2',     c: '' },
    { f: 'plezier3',   c: 'Tennisplezier'},  { f: 'plezier4',  c: '' }, { f: 'plezier5', c: '' },
    { f: 'competitie', c: 'Competitie' },   { f: 'groot_hart',c: '' },
    { f: 'pink_ladies',c: '' },             { f: 'wim',       c: '' },
  ];
  const gallery = sfeerImgs.map(o =>
    '<a href="images/sfeer/full/' + o.f + '.jpg" class="lb-trigger" aria-label="' + esc(o.c || 'Sfeerbeeld') + '">' +
    '<img src="images/sfeer/' + o.f + '.jpg" alt="' + esc(o.c) + '" onerror="this.parentElement.style.display=\'none\'">' +
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
  return '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px">' +
    '<img src="images/school/whackit.jpg" alt="WhackIt" style="width:100%;height:180px;object-fit:contain;background:#f9f9f9;border-radius:10px" onerror="this.style.display=\'none\'">' +
    '<img src="images/school/school3.jpg" alt="" style="width:100%;height:180px;object-fit:cover;object-position:center top;border-radius:10px" onerror="this.style.display=\'none\'">' +
    '<img src="images/school/school4.jpg" alt="" style="width:100%;height:180px;object-fit:cover;object-position:center top;border-radius:10px" onerror="this.style.display=\'none\'">' +
  '</div>' +
  '<div class="card" style="margin-bottom:16px"><div class="card-head">🎾 Tennisschool TC Kooike &times; WhackIt</div><div class="card-body">' +
    '<div>' +
        '<p style="font-size:.95rem;line-height:1.8;margin-bottom:12px">' +
        'TC Kooike organiseert, in samenwerking met tennisschool <strong>WhackIt</strong>, tennislessen die van start gaan in de <strong>week van 20 april 2026</strong>. ' +
        'Deze lessen zijn beschikbaar voor zowel jeugd als volwassenen.</p>' +
        '<p style="font-size:.9rem;font-weight:700;margin-bottom:6px;color:var(--clay-dark)">Wat bieden wij?</p>' +
        '<ul style="font-size:.9rem;line-height:2;margin:0 0 12px 18px;color:var(--text)">' +
          '<li><strong>Jeugdlessen</strong> – Voor zowel beginners als gevorderden.</li>' +
          '<li><strong>Competitielessen</strong> – Voor de echte wedstrijdspelers.</li>' +
          '<li><strong>Kleine groepen</strong> – Max. 4 spelers per trainer, persoonlijke aandacht.</li>' +
          '<li><strong>Leuke &amp; uitdagende trainingen</strong> – Tennis voor zowel plezier als groei!</li>' +
        '</ul>' +
        '<p style="font-size:.9rem;font-weight:700;margin-bottom:6px;color:var(--clay-dark)">Waarom kiezen voor TC Kooike?</p>' +
        '<ul style="font-size:.9rem;line-height:2;margin:0 0 0 18px;color:var(--text)">' +
          '<li>✅ Gediplomeerde en enthousiaste trainers</li>' +
          '<li>✅ Flexibele lesroosters, afgestemd op uw agenda</li>' +
          '<li>✅ Van basistechniek naar echte competitie</li>' +
        '</ul>' +
      '</div>' +
    '</div></div>' +
    '<div class="card"><div class="card-head">👧 Kids &amp; Tieners</div><div class="card-body">' +
    '<div class="tbl-wrap"><table class="school-tbl"><thead><tr><th>Groep</th><th>Formule</th><th>Prijs</th></tr></thead><tbody>' +
    '<tr><td>Blauw (4–5 jaar)</td><td>1u/week · 8 lessen</td><td>€100</td></tr>' +
    '<tr><td>Rood (6–8 jaar)</td><td>1u/week · 8 lessen</td><td>€100</td></tr>' +
    '<tr><td>Oranje (9–10 jaar)</td><td>1u/week · 8 lessen</td><td>€100</td></tr>' +
    '<tr><td>Groen (11–12 jaar)</td><td>1u/week · 8 lessen</td><td>€100</td></tr>' +
    '<tr><td>Geel – Tieners (13–18 j)</td><td>1u/week · 8 lessen</td><td>€100</td></tr>' +
    '<tr><td>Privé (1 speler)</td><td>1u/week · 8 lessen</td><td>€280</td></tr>' +
    '<tr><td>Privé (2 spelers)</td><td>1u/week · 8 lessen</td><td>€140 pp</td></tr>' +
    '</tbody></table></div>' +
    '<p class="help" style="margin-top:10px">Lessen op <strong>woensdagnamiddag</strong> (14u–18u) en <strong>zaterdag</strong> (10u–13u). ' +
    'Max. 4 spelers per trainer. Bij regenweer wordt de les uitgesteld.</p>' +
    '</div></div>' +
    '<div class="card"><div class="card-head">🧑 Volwassenen</div><div class="card-body">' +
    '<div class="tbl-wrap"><table class="school-tbl"><thead><tr><th>Formule</th><th>Omschrijving</th><th>Prijs</th></tr></thead><tbody>' +
    '<tr><td>Groepslessen beginners</td><td>1u/week · 8 lessen</td><td>€110 pp</td></tr>' +
    '<tr><td>Groepslessen (half-)gevorderden</td><td>1u/week · 8 lessen</td><td>€110 pp</td></tr>' +
    '<tr><td>Privé (1 speler)</td><td>1u/week · 8 lessen</td><td>€280</td></tr>' +
    '<tr><td>Privé (2 spelers)</td><td>1u/week · 8 lessen</td><td>€140 pp</td></tr>' +
    '<tr><td>Dubbeltraining (per 4)</td><td>Groep of individueel inschrijven</td><td>Op aanvraag</td></tr>' +
    '</tbody></table></div>' +
    '<p class="help" style="margin-top:10px">Groepslessen vereisen min. 3 spelers. Dubbeltraining ook individueel in te schrijven — TC Kooike stelt dan een groep samen op niveau.</p>' +
    '</div></div>' +
    '<a class="cta-btn" href="https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/doelgroep-details?clubId=2158&aanbodId=8043&doelgroepId=35211" target="_blank">✏️ Inschrijven tennisschool</a>';
}

function panelLadder() {
  const faq = [
    { q: 'Wat is de laddercompetitie?', a: 'Een leuke manier om jezelf sportief te meten met anderen. De lager geplaatste speler daagt een hoger geplaatste uit. Als de uitdager wint, stijgt zijn positie. Je eindpositie bepaalt de winnaar van het seizoen.' },
    { q: 'Hoe schrijf ik me in?', a: 'Via de website van Sportconnexions kun je inschrijven en aanduiden wanneer je beschikbaar bent en hoe snel het systeem wedstrijden mag inplannen.' },
    { q: 'Hoe daag ik een speler uit?', a: 'Het systeem loot zelf de wedstrijden — je hoeft niemand zelf uit te dagen.' },
    { q: 'Hoe plan ik een wedstrijd in?', a: 'Reserveer een baan via de app of website van Tennis & Padel Vlaanderen.' },
    { q: 'Wat telt als wedstrijd?', a: 'Je speelt 1–1,5 uur inclusief 5 min inspelen. Tel de games door. Bij gelijke stand na 1 uur speel je nog 1 beslissende game.' },
    { q: 'Waar voer ik de uitslag in?', a: 'In de laddercompetitie onder \'Wedstrijden\'. Doe dit binnen 10 dagen na de wedstrijd.' },
    { q: 'Wat als een speler geblesseerd raakt?', a: 'De tegenpartij wint de wedstrijd.' },
    { q: 'Wat als de score niet op tijd ingevuld is?', a: 'De eerstgenoemde speler zakt 1 plek. Neem tijdig contact op om dit te vermijden.' },
    { q: 'Wanneer kan ik spelen?', a: 'Elke dag. Overdag en in het weekend is er meer beschikbaarheid. Doordeweekse avonden zijn doorgaans drukker.' },
  ];
  const faqHtml = faq.map(f =>
    '<li><strong>' + esc(f.q) + '</strong>' + esc(f.a) + '</li>'
  ).join('');
  return '<div class="card"><div class="card-head">🪜 Laddercompetitie — Hoe werkt het?</div><div class="card-body">' +
    '<img src="images/ladder/ladder.png" alt="Laddercompetitie" class="ladder-img" onerror="this.style.display=\'none\'">' +
    '<p style="margin-bottom:14px;font-size:.9rem">De laddercompetitie is een uitstekende manier om je tennisspel te verbeteren, ' +
    'andere leden te leren kennen en jezelf sportief te meten — voor elk niveau!</p>' +
    '<ul class="faq-list">' + faqHtml + '</ul>' +
    '<a class="cta-btn" href="https://sportconnexions.com/nl/tennis/leagues/2556/" target="_blank">🪜 Inschrijven laddercompetitie</a>' +
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
  return '<div class="card"><div class="card-head">📞 Contact & Locatie — TC Kooike</div><div class="card-body">' +
    '<div class="info-grid">' +
      '<div class="info-card"><h3>📍 Adres</h3>' +
        '<div class="contact-block"><strong>TC Kooike</strong><br>Ertbrandstraat 58<br>2920 Kapellen</div>' +
        '<p class="help" style="margin-top:8px">Voldoende parking bij sporthal \'t Kooike.</p>' +
      '</div>' +
      '<div class="info-card"><h3>📧 E-mail & Telefoon</h3>' +
        '<div class="contact-block">' +
          '<a href="mailto:tckooike@gmail.com">tckooike@gmail.com</a><br>' +
          '<a href="tel:+32497891454">+32 497 89 14 54 (Steven)</a>' +
        '</div>' +
      '</div>' +
      '<div class="info-card"><h3>🔗 Handige links</h3>' +
        '<div class="contact-block">' +
          '<a href="https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/reserveer-een-terrein?clubId=2158" target="_blank">Terrein reserveren</a><br>' +
          '<a href="https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/lid-worden?clubId=2158" target="_blank">Lid worden</a><br>' +
        '</div>' +
      '</div>' +
    '</div>' +
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


def export_html(
    df_sched: pd.DataFrame,
    team_info_df: "pd.DataFrame | None",
    path: str,
    club_name: str = "Tennis Club",
    season: str = "Season 2026",
) -> None:
    """
    Export the schedule as a self-contained static HTML page for GitHub Pages.

    Features
    ---------
    - Tabbed navigation: Overview (all matches) + one tab per poule
    - Inline score entry — any numeric format (sets won, games, points…)
    - Live standings: W=2 pts, D=1, L=0; sorted by points then wins
    - Collapsible player / contact cards per poule
    - Scores auto-saved to the browser's localStorage
    - On page load, ``scores.json`` from the same directory is fetched as a
      baseline (commit it to GitHub Pages to share results with the whole club)
    - Export / Import buttons to exchange ``scores.json`` manually

    GitHub Pages workflow
    ----------------------
    1. Run the scheduler → ``output/schedule.html`` is generated alongside the
       Excel and PDF files.
    2. Copy ``output/schedule.html`` to your GitHub Pages repository and push.
    3. After entering match results, click **Export** → download ``scores.json``
       → commit it to the same folder → everyone sees updated standings on reload.
    """
    import json
    from datetime import date as _date

    poules = (
        sorted(df_sched["Poule"].unique())
        if "Poule" in df_sched.columns
        else [""]
    )

    # Build team-info lookup: team name → detail dict
    info_lkp: dict[str, dict] = {}
    if team_info_df is not None and not team_info_df.empty:
        for _, row in team_info_df.iterrows():
            name = str(row.get("Team", "") or "").strip()
            if name:
                info_lkp[name] = {
                    "player_1": str(row.get("Player 1", "") or "").strip(),
                    "player_2": str(row.get("Player 2", "") or "").strip(),
                    "tel_1":    str(row.get("Tel P1",   "") or "").strip(),
                    "tel_2":    str(row.get("Tel P2",   "") or "").strip(),
                }

    # Build teams_by_poule
    teams_by_poule: dict[str, list[dict]] = {}
    for poule in poules:
        df_p = (
            df_sched[df_sched["Poule"] == poule]
            if "Poule" in df_sched.columns and poule
            else df_sched
        )
        team_names = sorted(set(df_p["Team A"].tolist() + df_p["Team B"].tolist()))
        teams_by_poule[poule] = [
            {"name": t, **info_lkp.get(t, {})} for t in team_names
        ]

    # Build matches list
    matches = []
    for _, row in df_sched.iterrows():
        ta         = str(row["Team A"])
        tb         = str(row["Team B"])
        date_str   = str(row["Date"])
        time_str   = str(row["Time"])
        poule_str  = str(row.get("Poule", "")) if "Poule" in row.index else ""
        terrain    = str(row["Terrain"])
        mid = (
            f"{date_str}_{time_str}_{ta}_{tb}"
            .replace(" ", "_").replace(".", "_")
            .replace("&", "and").replace("/", "-")
        )
        matches.append({
            "id":      mid,
            "poule":   poule_str,
            "date":    date_str,
            "time":    time_str,
            "terrain": terrain,
            "team_a":  ta,
            "team_b":  tb,
        })

    interclub_matches = load_interclub_matches()

    data = {
        "club_name":      club_name,
        "season":         season,
        "generated":      str(_date.today()),
        "poules":         list(poules),
        "teams_by_poule": teams_by_poule,
        "matches":        matches,
      "interclub_matches": interclub_matches,
    }

    html = _HTML_TEMPLATE.replace("__SCHEDULE_DATA__", json.dumps(data, ensure_ascii=False))
    Path(path).write_text(html, encoding="utf-8")
    print(f"Saved HTML site to:    {path}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description="Poule competition scheduler using CP-SAT optimisation."
    )
    p.add_argument("--teams",   help="CSV with team names (column: Team)")
    p.add_argument("--avail",   help="CSV with team availabilities (Google Forms export)")
    p.add_argument("--slots",   help="CSV with terrain slot definitions")
    p.add_argument("--output",  default="schedule.xlsx", help="Output Excel file path")
    p.add_argument("--timelimit", type=int, default=60,
                   help="Solver time limit in seconds (default: 60)")
    return p.parse_args()


# ── Demo ───────────────────────────────────────────────────────────────────────

def _run_demo():
    """Built-in demo with 2 poules × 4 teams over 6 weeks."""
    print("Running built-in demo with 2 poules × 4 teams over 6 weeks...\n")

    # Venue: 6 Mondays, 3 time slots per evening, 4 terrains each
    dates = [
        "2026-05-04", "2026-05-11", "2026-05-18",
        "2026-05-25", "2026-06-01", "2026-06-08",
    ]
    times = ["18:00", "19:30", "21:00"]
    terrain_slots = generate_terrain_slots(
        dates, times, n_terrains=4,
        terrain_overrides={"2026-05-25": 2}   # only 2 terrains available that week
    )

    poules = {
        "A": ["Alpha", "Bravo", "Charlie", "Delta"],
        "B": ["Echo", "Foxtrot", "Golf", "Hotel"],
    }
    all_teams = [t for ts in poules.values() for t in ts]

    # Simulate availability: each team randomly available at ~60 % of slots
    all_slot_labels = list(dict.fromkeys(s["slot"] for s in terrain_slots))
    rng = random.Random(42)
    team_avail = {
        team: set(sl for sl in all_slot_labels if rng.random() < 0.60)
        for team in all_teams
    }

    print("Team availabilities (number of available slots):")
    for poule_name, teams in poules.items():
        print(f"  Poule {poule_name}:")
        for team in teams:
            print(f"    {team:10s}: {len(team_avail[team]):2d} / {len(all_slot_labels)} slots")
    print()

    scheduled, unscheduled = schedule(
        poules, team_avail, terrain_slots, time_limit_s=30
    )

    df_sched, df_unsched = to_dataframes(scheduled, unscheduled)
    print_schedule(df_sched)
    export_excel(df_sched, df_unsched, "schedule_demo.xlsx")
    export_schedule_overview_pdf(df_sched, "schedule_demo_overview.pdf",
                                 club_name="TC Kooike", season="Seizoen 2026")
    export_pdf(df_sched, None, "schedule_demo.pdf",
               club_name="TC Kooike", season="Seizoen 2026")
    export_html(df_sched, None, "schedule_demo.html",
                club_name="TC Kooike", season="Seizoen 2026")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    args = _parse_args()

    # If no arguments given, run the demo
    if not any([args.teams, args.avail, args.slots]):
        _run_demo()
        return

    missing = [flag for flag, val in [("--teams", args.teams),
                                       ("--avail", args.avail),
                                       ("--slots", args.slots)] if not val]
    if missing:
        print(f"Error: missing required arguments: {', '.join(missing)}")
        print("Run without arguments for a built-in demo.")
        return

    teams_by_poule, team_info_df = load_teams(args.teams)
    all_teams      = [t for ts in teams_by_poule.values() for t in ts]
    team_avail     = load_team_availabilities(args.avail)
    terrain_sl     = load_terrain_slots(args.slots)

    n_poules = len(teams_by_poule)
    print(f"Loaded {n_poules} poule(s), {len(all_teams)} teams total, {len(terrain_sl)} terrain slots.")

    scheduled, unscheduled = schedule(
        teams_by_poule, team_avail, terrain_sl, time_limit_s=args.timelimit
    )

    df_sched, df_unsched = to_dataframes(scheduled, unscheduled)
    print_schedule(df_sched)
    export_excel(df_sched, df_unsched, args.output, team_info_df=team_info_df)
    pdf_path = args.output.replace(".xlsx", ".pdf")
    overview_pdf_path = args.output.replace(".xlsx", "_overview.pdf")
    html_path = args.output.replace(".xlsx", ".html")
    export_schedule_overview_pdf(df_sched, overview_pdf_path,
                                 club_name="TC Kooike", season="Seizoen 2026")
    export_pdf(df_sched, team_info_df, pdf_path,
               club_name="TC Kooike", season="Seizoen 2026")
    export_html(df_sched, team_info_df, html_path,
                club_name="TC Kooike", season="Seizoen 2026")


if __name__ == "__main__":
    main()

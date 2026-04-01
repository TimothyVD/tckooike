# Competition Scheduler

Schedules internal poule-format competitions using **constraint programming (CP-SAT)**
from Google OR-Tools. Loads team availabilities from a Google Forms CSV export and
terrain slot definitions, then finds an optimal match schedule that:

- Only schedules intra-poule (round-robin) matches
- Respects team availability
- Assigns at most one match per (slot, terrain) pair
- Limits each team to at most one match per calendar day
- Maximises the total number of scheduled matches

Multiple poules are supported and compete for the same venue slots.

---

## Folder structure

```
competition_scheduler/
├── competition_scheduler.py      ← main script
├── requirements.txt              ← Python dependencies
├── README.md                     ← this file
├── input/
│   ├── example_teams.csv                  ← team names + poule assignments
│   ├── example_team_availabilities.csv    ← availability per team (Google Forms format)
│   └── example_terrain_slots.csv          ← terrain slot definitions
└── output/
    ├── schedule_demo.xlsx         ← output of the built-in demo
    └── schedule_example.xlsx      ← output of the example CSV run
```

---

## Installation

```bash
pip install -r requirements.txt
```

Or install packages individually:

```bash
pip install ortools pandas openpyxl
```

---

## Usage

### Built-in demo (no files needed)

Runs a synthetic scenario with 2 poules × 4 teams over 6 weeks:

```bash
python3 competition_scheduler.py
```

### From CSV files

```bash
python3 competition_scheduler.py \
  --teams  input/example_teams.csv \
  --avail  input/example_team_availabilities.csv \
  --slots  input/example_terrain_slots.csv \
  --output output/schedule.xlsx
```

| Argument | Description |
|---|---|
| `--teams` | CSV with team names and poule assignments |
| `--avail` | CSV with team availabilities (Google Forms export) |
| `--slots` | CSV with terrain slot definitions |
| `--output` | Output Excel file (default: `schedule.xlsx`) |
| `--timelimit` | Solver time limit in seconds (default: 60) |

---

## Input file formats

### `input/example_teams.csv` — teams, poule assignments, and player info

Column order is **flexible** — columns are matched by name (case-insensitive).

| Column | Required | Description |
|---|---|---|
| `Team` | yes | Team name (must match names in the availability CSV) |
| `Poule` | no | Poule identifier (defaults to `A` if column is absent) |
| `player_1` | no | Name of first player |
| `player_2` | no | Name of second player |
| `ranking_player_1` | no | Ranking / level of player 1 |
| `ranking_player_2` | no | Ranking / level of player 2 |
| `tel_player_1` | no | Phone number of player 1 |
| `tel_player_2` | no | Phone number of player 2 |

Any combination of optional columns is accepted, in any order. Absent columns are simply omitted from the output.

```
Poule,Team,player_1,player_2,ranking_player_1,ranking_player_2,tel_player_1,tel_player_2
A,Alpha,Alice Dupont,Bob Martin,R4,R5,+32 470 11 22 33,+32 471 44 55 66
A,Bravo,Carol Leroy,David Petit,R5,R6,+32 472 77 88 99,+32 473 00 11 22
B,Delta,Grace Simon,Hugo Laurent,R5,R5,+32 476 99 00 11,+32 477 22 33 44
```

Team information is written to a dedicated **Teams** sheet (green header) in the output Excel file.

### `input/example_team_availabilities.csv` — team availabilities

Directly matches the **Google Forms checkbox-grid CSV export**.

**Format A — one column per slot (recommended for Google Forms):**

```
Team,2026-05-04 18:00,2026-05-04 19:30,2026-05-11 18:00,...
Alpha,TRUE,,TRUE,...
Bravo,,TRUE,TRUE,...
```

Slot column headers must use the format `YYYY-MM-DD HH:MM`, matching exactly
what is used in the terrain slots CSV.

**Format B — comma-separated list in a single cell:**

```
Team,Available slots
Alpha,"2026-05-04 18:00, 2026-05-11 18:00"
Bravo,"2026-05-04 19:30"
```

### `input/example_terrain_slots.csv` — terrain/time slot definitions

| Column | Description |
|---|---|
| `date` | Date in `YYYY-MM-DD` format |
| `time` | Start time in `HH:MM` format |
| `terrain_id` | Integer terrain number (1, 2, 3, …) |

Each row = one available (slot, terrain) pair. Add or remove rows to adjust
the number of terrains or time slots for any given date.

```
date,time,terrain_id
2026-05-04,18:00,1
2026-05-04,18:00,2
2026-05-04,18:00,3
2026-05-04,18:00,4
2026-05-04,19:30,1
...
```

---

## Output Excel file

The generated `.xlsx` workbook contains:

| Sheet | Contents |
|---|---|
| **Teams** | Team and player info with rankings and phone numbers (green header; only when `--teams` CSV is provided) |
| **Schedule** | Full schedule sorted by poule, date, time, terrain |
| **By Team** | Per-team match list (one row per match per team) |
| **Poule A / B / …** | One sheet per poule (only when multiple poules exist) |
| **Unscheduled** | Matches that could not be placed due to availability conflicts (if any) |

---

## Google Forms setup

1. Create a form with a **short-answer** question for the team name.
2. Add a **checkbox grid** question:
   - Rows = dates (e.g., `2026-05-04`)
   - Columns = time slots (e.g., `18:00`, `19:30`, `21:00`)
3. Export responses: Google Sheets → **File → Download → Comma-separated values**.
4. Rename the team-name column header to `Team` and reformat slot column headers
   to `YYYY-MM-DD HH:MM` (combine the date row and time column headers).

---

## Programmatic use

```python
from competition_scheduler import (
    generate_terrain_slots,
    schedule,
    to_dataframes,
    print_schedule,
    export_excel,
)

poules = {
    "A": ["Alpha", "Bravo", "Charlie"],
    "B": ["Delta", "Echo", "Foxtrot"],
}

terrain_slots = generate_terrain_slots(
    dates=["2026-05-04", "2026-05-11", "2026-05-18"],
    times=["18:00", "19:30", "21:00"],
    n_terrains=4,
    terrain_overrides={"2026-05-11": 2},  # only 2 terrains that week
)

team_avail = {
    "Alpha":   {"2026-05-04 18:00", "2026-05-11 19:30"},
    "Bravo":   {"2026-05-04 19:30", "2026-05-18 18:00"},
    # ...
}

scheduled, unscheduled = schedule(poules, team_avail, terrain_slots)
df_sched, df_unsched = to_dataframes(scheduled, unscheduled)
print_schedule(df_sched)
export_excel(df_sched, df_unsched, "output/schedule.xlsx")
```

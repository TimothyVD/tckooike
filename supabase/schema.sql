-- TC Kooike Zomercompetitie — match result submission schema.
-- Paste into the Supabase SQL editor and run once. Safe to re-run
-- (tables/functions use IF NOT EXISTS / OR REPLACE; policies are dropped
-- and recreated so this script is idempotent even if you already created
-- the tables manually via the Table Editor).

create extension if not exists pgcrypto;

-- ── matches ──────────────────────────────────────────────
-- Mirrors input/schedule.json's matches array. Needed so the server can
-- independently verify which two teams a given match_id really involves —
-- never trust the client's claim about team_a/team_b.
create table if not exists matches (
  match_id   text primary key,
  poule      text not null,
  match_date date not null,
  match_time text not null,
  terrain    text,
  team_a     text not null,
  team_b     text not null
);

alter table matches enable row level security;

drop policy if exists "matches_select_anon" on matches;
create policy "matches_select_anon" on matches for select to anon using (true);
-- No write policy for anon — only the sync script (service_role, bypasses RLS) writes here.

-- ── teams (codes) — zero anon access, by design ─────────
-- Holds bcrypt-hashed access codes. No policy at all is granted to anon,
-- so RLS blocks every direct read/write from the browser. The only access
-- path is through submit_result() below, which runs as SECURITY DEFINER.
create table if not exists teams (
  team_name        text primary key,
  poule            text not null,
  access_code_hash text not null
);

alter table teams enable row level security;
-- Deliberately no policies created here for anon.

-- ── results — one row per match ─────────────────────────
-- match_id is the primary key, which is the entire "first submission
-- wins" mechanism: a second insert for the same match fails on the PK
-- constraint with no extra locking needed.
create table if not exists results (
  match_id          text primary key references matches(match_id),
  winner_side       text not null check (winner_side in ('a', 'b')),
  set1_w int not null, set1_l int not null,
  set2_w int not null, set2_l int not null,
  set3_w int, set3_l int,
  submitted_by_team text not null,
  submitted_at      timestamptz not null default now()
);

alter table results enable row level security;

drop policy if exists "results_select_anon" on results;
create policy "results_select_anon" on results for select to anon using (true);
-- No write policy for anon — all writes go through submit_result() below.

-- ── auth_attempts — brute-force throttle ────────────────
-- Records failed access-code attempts per match. submit_result() and
-- reschedule_match() count recent failures for a match and refuse further
-- tries once a burst threshold is hit, so an attacker can't grind guesses
-- against a match's two codes. RLS on with no anon policy: only the
-- SECURITY DEFINER functions (which bypass RLS) ever touch this table.
create table if not exists auth_attempts (
  id           bigint generated always as identity primary key,
  match_id     text not null,
  attempted_at timestamptz not null default now()
);
create index if not exists auth_attempts_match_time on auth_attempts (match_id, attempted_at);

alter table auth_attempts enable row level security;
-- Deliberately no policies for anon.

-- ── validation helpers ──────────────────────────────────
-- Mirror isValidSet/isValidTiebreak in site_template.html exactly:
--   regular set: winner reaches 6 (loser <=4), or 7-5, or 7-6 (tiebreak set)
--   match-tiebreak (3rd "set"): winner reaches >=10, win by >=2
create or replace function _valid_set(w int, l int) returns boolean
language sql immutable as $$
  select w is not null and l is not null
     and ((greatest(w,l) = 6 and least(w,l) <= 4)
       or (greatest(w,l) = 7 and least(w,l) in (5,6)));
$$;

create or replace function _valid_tiebreak(w int, l int) returns boolean
language sql immutable as $$
  select w is not null and l is not null
     and greatest(w,l) >= 10 and (greatest(w,l) - least(w,l)) >= 2;
$$;

-- ── the only write path ──────────────────────────────────
-- Scores are passed in WINNER-PERSPECTIVE order (winner's games/points
-- first in each set pair); p_winner_side says which of team_a/team_b that
-- winner actually is, so the function can map back onto team_a/team_b
-- ordering before storing.
create or replace function submit_result(
  p_match_id    text,
  p_access_code text,
  p_winner_side text,
  p_set1_w int, p_set1_l int,
  p_set2_w int, p_set2_l int,
  p_set3_w int default null, p_set3_l int default null
) returns jsonb
language plpgsql security definer set search_path = public, extensions
as $$
declare
  v_match matches%rowtype;
  v_team  teams%rowtype;
  v_wins  int := 0;
  v_a1w int; v_a1l int; v_a2w int; v_a2l int; v_a3w int; v_a3l int;
begin
  if p_winner_side not in ('a', 'b') then
    return jsonb_build_object('success', false, 'error', 'Ongeldige winnaarskeuze.');
  end if;

  select * into v_match from matches where match_id = p_match_id;
  if v_match.match_id is null then
    return jsonb_build_object('success', false, 'error', 'Wedstrijd niet gevonden.');
  end if;

  if exists (select 1 from results where match_id = p_match_id) then
    return jsonb_build_object('success', false, 'error', 'Resultaat voor deze wedstrijd werd al doorgegeven.');
  end if;

  -- Brute-force throttle: refuse further tries after several recent failures
  -- for this match (old rows purged first).
  delete from auth_attempts where attempted_at < now() - interval '15 minutes';
  if (select count(*) from auth_attempts
        where match_id = p_match_id and attempted_at > now() - interval '15 minutes') >= 6 then
    return jsonb_build_object('success', false,
      'error', 'Te veel mislukte pogingen voor deze wedstrijd. Probeer het over een kwartier opnieuw.');
  end if;

  -- Scoped to the 2 teams of THIS match only — cheap even with many teams,
  -- since bcrypt verification is deliberately slow per row checked.
  select * into v_team from teams
   where team_name in (v_match.team_a, v_match.team_b)
     and access_code_hash = crypt(p_access_code, access_code_hash)
   limit 1;
  if v_team.team_name is null then
    insert into auth_attempts (match_id) values (p_match_id);
    return jsonb_build_object('success', false, 'error', 'Ongeldige toegangscode.');
  end if;
  -- Valid code: reset this match's failure counter.
  delete from auth_attempts where match_id = p_match_id;

  if not _valid_set(p_set1_w, p_set1_l) then
    return jsonb_build_object('success', false, 'error', 'Set 1 is geen geldige setuitslag.');
  end if;
  if not _valid_set(p_set2_w, p_set2_l) then
    return jsonb_build_object('success', false, 'error', 'Set 2 is geen geldige setuitslag.');
  end if;
  if (p_set3_w is not null or p_set3_l is not null) and not _valid_tiebreak(p_set3_w, p_set3_l) then
    return jsonb_build_object('success', false, 'error', 'De 3e set (MTB10) is geen geldige tiebreakuitslag.');
  end if;

  -- Note: the declared winner CAN have a lower number in an individual set
  -- (e.g. they lost set 1 but won the match) — only the aggregate sets-won
  -- count below matters, never reject based on a single set's ordering.

  -- The core "verify the winner actually gets the two points" check.
  if p_set1_w > p_set1_l then v_wins := v_wins + 1; end if;
  if p_set2_w > p_set2_l then v_wins := v_wins + 1; end if;
  if p_set3_w is not null and p_set3_l is not null and p_set3_w > p_set3_l then
    v_wins := v_wins + 1;
  end if;
  if v_wins < 2 then
    return jsonb_build_object('success', false, 'error', 'Deze sets leveren geen 2-setoverwinning op voor de aangeduide winnaar.');
  end if;

  if p_winner_side = 'a' then
    v_a1w := p_set1_w; v_a1l := p_set1_l; v_a2w := p_set2_w; v_a2l := p_set2_l; v_a3w := p_set3_w; v_a3l := p_set3_l;
  else
    v_a1w := p_set1_l; v_a1l := p_set1_w; v_a2w := p_set2_l; v_a2l := p_set2_w; v_a3w := p_set3_l; v_a3l := p_set3_w;
  end if;

  insert into results (match_id, winner_side, set1_w, set1_l, set2_w, set2_l, set3_w, set3_l, submitted_by_team)
  values (p_match_id, p_winner_side, v_a1w, v_a1l, v_a2w, v_a2l, v_a3w, v_a3l, v_team.team_name);

  return jsonb_build_object('success', true);
exception
  when unique_violation then
    return jsonb_build_object('success', false, 'error', 'Resultaat voor deze wedstrijd werd net al doorgegeven.');
end;
$$;

grant execute on function submit_result(text, text, text, int, int, int, int, int, int) to anon;

-- ── reschedules — team-initiated match moves ────────────
-- A live override layer on top of matches. A team can move one of their OWN
-- matches to a new date/time; match_id stays stable (it still references the
-- original slot, so an already-submitted result never gets orphaned), only
-- the date/time shown on the site changes. Terrain is cleared to '?' because
-- the two teams re-book the court themselves via Tennis & Padel Vlaanderen.
--
-- By design there are NO scheduling-conflict checks (terrain capacity, double
-- bookings, shared players): the teams coordinate the move between themselves.
-- The only gate is that the access code must belong to one of the two teams.
create table if not exists reschedules (
  match_id            text primary key references matches(match_id) on delete cascade,
  new_date            date not null,
  new_time            text not null,
  rescheduled_by_team text not null,
  rescheduled_at      timestamptz not null default now()
);

alter table reschedules enable row level security;

drop policy if exists "reschedules_select_anon" on reschedules;
create policy "reschedules_select_anon" on reschedules for select to anon using (true);
-- No anon write policy — all writes go through reschedule_match() below.

create or replace function reschedule_match(
  p_match_id    text,
  p_access_code text,
  p_new_date    date,
  p_new_time    text
) returns jsonb
language plpgsql security definer set search_path = public, extensions
as $$
declare
  v_match matches%rowtype;
  v_team  teams%rowtype;
begin
  select * into v_match from matches where match_id = p_match_id;
  if v_match.match_id is null then
    return jsonb_build_object('success', false, 'error', 'Wedstrijd niet gevonden.');
  end if;

  -- A match that already has a result has been played — it can't be moved.
  -- (This is a data-integrity guard, not a scheduling check.)
  if exists (select 1 from results where match_id = p_match_id) then
    return jsonb_build_object('success', false, 'error', 'Deze wedstrijd heeft al een resultaat en kan niet meer verzet worden.');
  end if;

  -- Brute-force throttle: refuse further tries after several recent failures
  -- for this match (old rows purged first).
  delete from auth_attempts where attempted_at < now() - interval '15 minutes';
  if (select count(*) from auth_attempts
        where match_id = p_match_id and attempted_at > now() - interval '15 minutes') >= 6 then
    return jsonb_build_object('success', false,
      'error', 'Te veel mislukte pogingen voor deze wedstrijd. Probeer het over een kwartier opnieuw.');
  end if;

  -- Access code must belong to one of the two teams in this match. Scoped to
  -- just those 2 teams so bcrypt is only run twice at most.
  select * into v_team from teams
   where team_name in (v_match.team_a, v_match.team_b)
     and access_code_hash = crypt(p_access_code, access_code_hash)
   limit 1;
  if v_team.team_name is null then
    insert into auth_attempts (match_id) values (p_match_id);
    return jsonb_build_object('success', false, 'error', 'Ongeldige toegangscode.');
  end if;
  -- Valid code: reset this match's failure counter.
  delete from auth_attempts where match_id = p_match_id;

  if p_new_date is null or p_new_time is null or p_new_time !~ '^[0-2][0-9]:[0-5][0-9]$' then
    return jsonb_build_object('success', false, 'error', 'Ongeldige datum of tijd.');
  end if;

  insert into reschedules (match_id, new_date, new_time, rescheduled_by_team)
  values (p_match_id, p_new_date, p_new_time, v_team.team_name)
  on conflict (match_id) do update
    set new_date            = excluded.new_date,
        new_time            = excluded.new_time,
        rescheduled_by_team = excluded.rescheduled_by_team,
        rescheduled_at      = now();

  return jsonb_build_object('success', true);
end;
$$;

grant execute on function reschedule_match(text, text, date, text) to anon;

/**
 * TC Kooike — Poulecompetitie: Google Form creator & CSV exporter
 * ================================================================
 * HOW TO USE
 * ----------
 * 1. Go to https://script.google.com and create a new project.
 * 2. Paste this entire file into the editor.
 * 3. Run createForm() → a Google Form is created in your Drive.
 * 4. Share the form link with all team captains.
 * 5. After collecting responses, run exportToCSV().
 *    Two files appear in your Google Drive root:
 *      - teams.csv               → use with --teams
 *      - team_availabilities.csv → use with --avail
 */


// ══════════════════════════════════════════════════════════════════
//  CONFIGURATION  — edit this block before running
// ══════════════════════════════════════════════════════════════════

const CONFIG = {
  formTitle: 'TC Kooike – Poulecompetitie 2026: Teamgegevens & Beschikbaarheid',

  poules: ['DG', 'DD', 'DH'],

  // ── Vrijdagen: 26 jun → 28 aug ──────────────────────────────────
  friday_dates: [
    { label: 'vr 26 jun 2026', value: '2026-06-26' },
    { label: 'vr  3 jul 2026', value: '2026-07-03' },
    { label: 'vr 10 jul 2026', value: '2026-07-10' },
    { label: 'vr 17 jul 2026', value: '2026-07-17' },
    { label: 'vr 24 jul 2026', value: '2026-07-24' },
    { label: 'vr 31 jul 2026', value: '2026-07-31' },
    { label: 'vr  7 aug 2026', value: '2026-08-07' },
    { label: 'vr 14 aug 2026', value: '2026-08-14' },
    { label: 'vr 21 aug 2026', value: '2026-08-21' },
    { label: 'vr 28 aug 2026', value: '2026-08-28' },
  ],
  friday_times: ['17:00', '18:30', '20:00'],

  // ── Zaterdagen: 27 jun → 29 aug ─────────────────────────────────
  saturday_dates: [
    { label: 'za 27 jun 2026', value: '2026-06-27' },
    { label: 'za  4 jul 2026', value: '2026-07-04' },
    { label: 'za 11 jul 2026', value: '2026-07-11' },
    { label: 'za 18 jul 2026', value: '2026-07-18' },
    { label: 'za 25 jul 2026', value: '2026-07-25' },
    { label: 'za  1 aug 2026', value: '2026-08-01' },
    { label: 'za  8 aug 2026', value: '2026-08-08' },
    { label: 'za 15 aug 2026', value: '2026-08-15' },
    { label: 'za 22 aug 2026', value: '2026-08-22' },
    { label: 'za 29 aug 2026', value: '2026-08-29' },
  ],
  saturday_times: ['10:00', '11:30', '13:00', '14:30', '16:00', '17:30'],

  // ── Zondagen: 28 jun → 30 aug ───────────────────────────────────
  sunday_dates: [
    { label: 'zo 28 jun 2026', value: '2026-06-28' },
    { label: 'zo  5 jul 2026', value: '2026-07-05' },
    { label: 'zo 12 jul 2026', value: '2026-07-12' },
    { label: 'zo 19 jul 2026', value: '2026-07-19' },
    { label: 'zo 26 jul 2026', value: '2026-07-26' },
    { label: 'zo  2 aug 2026', value: '2026-08-02' },
    { label: 'zo  9 aug 2026', value: '2026-08-09' },
    { label: 'zo 16 aug 2026', value: '2026-08-16' },
    { label: 'zo 23 aug 2026', value: '2026-08-23' },
    { label: 'zo 30 aug 2026', value: '2026-08-30' },
  ],
  sunday_times: ['10:00', '11:30', '13:00', '14:30', '16:00', '17:30'],
};

// Grid question titles — used by both createForm() and exportToCSV()
const GRID_TITLES = {
  friday:   'Beschikbaarheid — vrijdagen',
  saturday: 'Beschikbaarheid — zaterdagen',
  sunday:   'Beschikbaarheid — zondagen',
};


// ══════════════════════════════════════════════════════════════════
//  createForm()  — run once to generate the Google Form
// ══════════════════════════════════════════════════════════════════

function createForm() {
  const form = FormApp.create(CONFIG.formTitle);
  form.setDescription(
    'Vul dit formulier in voor jouw team in de poulecompetitie van TC Kooike. ' +
    'Vink alle datum/tijdcombinaties aan waarop jouw team beschikbaar is.'
  );
  form.setCollectEmail(false);
  form.setLimitOneResponsePerUser(false);

  // ── Team info ──────────────────────────────────────────────────
  form.addMultipleChoiceItem()
    .setTitle('Poule')
    .setChoiceValues(CONFIG.poules)
    .setRequired(true);

  // ── Player 1 ───────────────────────────────────────────────────
  form.addSectionHeaderItem().setTitle('Speler 1');

  form.addTextItem()
    .setTitle('Naam speler 1')
    .setRequired(true);

  form.addTextItem()
    .setTitle('Telefoonnummer speler 1')
    .setHelpText('Zodat de andere kapitein contact kan opnemen.')
    .setRequired(true);

  // ── Player 2 ───────────────────────────────────────────────────
  form.addSectionHeaderItem().setTitle('Speler 2');

  form.addTextItem()
    .setTitle('Naam speler 2')
    .setRequired(true);

  form.addTextItem()
    .setTitle('Telefoonnummer speler 2')
    .setRequired(false);

  // ── Availability grids ─────────────────────────────────────────
  form.addSectionHeaderItem()
    .setTitle('Beschikbaarheid')
    .setHelpText(
      'Vink alle momenten aan waarop jouw team een wedstrijd kan spelen. ' +
      'Hoe meer vakjes, hoe makkelijker de planning!'
    );

  form.addCheckboxGridItem()
    .setTitle(GRID_TITLES.friday)
    .setRows(CONFIG.friday_dates.map(d => d.label))
    .setColumns(CONFIG.friday_times)
    .setRequired(false);

  form.addCheckboxGridItem()
    .setTitle(GRID_TITLES.saturday)
    .setRows(CONFIG.saturday_dates.map(d => d.label))
    .setColumns(CONFIG.saturday_times)
    .setRequired(false);

  form.addCheckboxGridItem()
    .setTitle(GRID_TITLES.sunday)
    .setRows(CONFIG.sunday_dates.map(d => d.label))
    .setColumns(CONFIG.sunday_times)
    .setRequired(false);

  const url = form.getPublishedUrl();
  Logger.log('✅ Form created!');
  Logger.log('Share this link with team captains: ' + url);
  Logger.log('Edit the form here: ' + form.getEditUrl());
}


// ══════════════════════════════════════════════════════════════════
//  exportToCSV()  — run after collecting responses
//  Writes teams.csv and team_availabilities.csv to your Drive root
// ══════════════════════════════════════════════════════════════════

function exportToCSV() {
  const form = FormApp.getActiveForm();
  const responses = form.getResponses();

  if (responses.length === 0) {
    Logger.log('No responses yet.');
    return;
  }

  // Build all slots from each day group, then sort chronologically
  const dayGroups = [
    { dates: CONFIG.friday_dates,   times: CONFIG.friday_times,   title: GRID_TITLES.friday   },
    { dates: CONFIG.saturday_dates, times: CONFIG.saturday_times, title: GRID_TITLES.saturday },
    { dates: CONFIG.sunday_dates,   times: CONFIG.sunday_times,   title: GRID_TITLES.sunday   },
  ];

  const slotObjs = [];
  for (const g of dayGroups) {
    for (let di = 0; di < g.dates.length; di++) {
      for (const t of g.times) {
        slotObjs.push({ slot: g.dates[di].value + ' ' + t, dateIdx: di, time: t, group: g });
      }
    }
  }
  slotObjs.sort((a, b) => (a.slot < b.slot ? -1 : a.slot > b.slot ? 1 : 0));
  const slots = slotObjs.map(o => o.slot);

  // CSV headers — Team is derived from player names (no explicit team name field)
  const teamRows  = [['Team', 'Poule', 'player_1', 'tel_player_1', 'player_2', 'tel_player_2']];
  const availRows = [['Team', ...slots]];

  for (const response of responses) {
    const items = response.getItemResponses();

    let poule = '', p1 = '', tel1 = '', p2 = '', tel2 = '';
    const grids = {};  // { gridTitle: String[][] }

    for (const item of items) {
      const title = item.getItem().getTitle();
      const val   = item.getResponse();
      switch (title) {
        case 'Poule':                      poule = val; break;
        case 'Naam speler 1':              p1    = val; break;
        case 'Telefoonnummer speler 1':    tel1  = val; break;
        case 'Naam speler 2':              p2    = val; break;
        case 'Telefoonnummer speler 2':    tel2  = val; break;
        case GRID_TITLES.friday:
        case GRID_TITLES.saturday:
        case GRID_TITLES.sunday:
          grids[title] = val;  // 2D: grid[dateIndex] = [checkedTime, ...]
          break;
      }
    }

    // Derive team name from player names
    const team = p2 ? p1 + ' / ' + p2 : p1;

    teamRows.push([team, poule, p1, tel1, p2, tel2]);

    // One column per slot: TRUE if checked, empty otherwise
    const availRow = [team];
    for (const obj of slotObjs) {
      const grid    = grids[obj.group.title];
      const checked = grid && grid[obj.dateIdx] && grid[obj.dateIdx].includes(obj.time);
      availRow.push(checked ? 'TRUE' : '');
    }
    availRows.push(availRow);
  }

  // Write files to Drive root
  const folder = DriveApp.getRootFolder();
  writeCSV(folder, 'teams.csv',               teamRows);
  writeCSV(folder, 'team_availabilities.csv', availRows);

  Logger.log('✅ Exported ' + responses.length + ' response(s) to your Drive root.');
  Logger.log('Download teams.csv and team_availabilities.csv, then run:');
  Logger.log(
    'python competition_scheduler.py ' +
    '--teams teams.csv ' +
    '--avail team_availabilities.csv ' +
    '--slots input/example_terrain_slots.csv ' +
    '--output output/schedule.xlsx'
  );
}


// ── Helper ────────────────────────────────────────────────────────

function writeCSV(folder, filename, rows) {
  const csv = rows.map(row =>
    row.map(cell => {
      const s = String(cell == null ? '' : cell);
      return (s.includes(',') || s.includes('"') || s.includes('\n'))
        ? '"' + s.replace(/"/g, '""') + '"'
        : s;
    }).join(',')
  ).join('\n');

  const existing = folder.getFilesByName(filename);
  while (existing.hasNext()) existing.next().setTrashed(true);

  folder.createFile(filename, csv, MimeType.PLAIN_TEXT);
  Logger.log('Wrote ' + filename + ' (' + (rows.length - 1) + ' rows)');
}

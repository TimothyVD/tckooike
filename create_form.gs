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

  poules: ['A', 'B', 'C'],

  // All match dates in chronological order (vr/za/zo: 26 jun → 30 aug 2026)
  dates: [
    { label: 'vr 26 jun 2026', value: '2026-06-26' },
    { label: 'za 27 jun 2026', value: '2026-06-27' },
    { label: 'zo 28 jun 2026', value: '2026-06-28' },
    { label: 'vr  3 jul 2026', value: '2026-07-03' },
    { label: 'za  4 jul 2026', value: '2026-07-04' },
    { label: 'zo  5 jul 2026', value: '2026-07-05' },
    { label: 'vr 10 jul 2026', value: '2026-07-10' },
    { label: 'za 11 jul 2026', value: '2026-07-11' },
    { label: 'zo 12 jul 2026', value: '2026-07-12' },
    { label: 'vr 17 jul 2026', value: '2026-07-17' },
    { label: 'za 18 jul 2026', value: '2026-07-18' },
    { label: 'zo 19 jul 2026', value: '2026-07-19' },
    { label: 'vr 24 jul 2026', value: '2026-07-24' },
    { label: 'za 25 jul 2026', value: '2026-07-25' },
    { label: 'zo 26 jul 2026', value: '2026-07-26' },
    { label: 'vr 31 jul 2026', value: '2026-07-31' },
    { label: 'za  1 aug 2026', value: '2026-08-01' },
    { label: 'zo  2 aug 2026', value: '2026-08-02' },
    { label: 'vr  7 aug 2026', value: '2026-08-07' },
    { label: 'za  8 aug 2026', value: '2026-08-08' },
    { label: 'zo  9 aug 2026', value: '2026-08-09' },
    { label: 'vr 14 aug 2026', value: '2026-08-14' },
    { label: 'za 15 aug 2026', value: '2026-08-15' },
    { label: 'zo 16 aug 2026', value: '2026-08-16' },
    { label: 'vr 21 aug 2026', value: '2026-08-21' },
    { label: 'za 22 aug 2026', value: '2026-08-22' },
    { label: 'zo 23 aug 2026', value: '2026-08-23' },
    { label: 'vr 28 aug 2026', value: '2026-08-28' },
    { label: 'za 29 aug 2026', value: '2026-08-29' },
    { label: 'zo 30 aug 2026', value: '2026-08-30' },
  ],

  // Time slots — same columns for every date
  times: ['10:00', '11:30', '13:00', '14:30', '16:00', '17:30', '19:00', '20:30'],
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
  form.addTextItem()
    .setTitle('Teamnaam')
    .setHelpText('Voer de volledige teamnaam in (bv. "Dupont / Martin").')
    .setRequired(true);

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
    .setHelpText('Optioneel, maar handig voor de kapitein.')
    .setRequired(false);

  // ── Player 2 ───────────────────────────────────────────────────
  form.addSectionHeaderItem().setTitle('Speler 2');

  form.addTextItem()
    .setTitle('Naam speler 2')
    .setRequired(false);

  form.addTextItem()
    .setTitle('Telefoonnummer speler 2')
    .setRequired(false);

  // ── Availability grid ──────────────────────────────────────────
  form.addSectionHeaderItem()
    .setTitle('Beschikbaarheid')
    .setHelpText(
      'Vink alle momenten aan waarop jouw team een wedstrijd kan spelen. ' +
      'Hoe meer vakjes, hoe makkelijker de planning!'
    );

  form.addCheckboxGridItem()
    .setTitle('Op welke data en tijdstippen is jouw team beschikbaar?')
    .setRows(CONFIG.dates.map(d => d.label))
    .setColumns(CONFIG.times)
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

  // Build the full list of slot column headers: ['2026-06-26 10:00', ...]
  const slots = [];
  for (const d of CONFIG.dates) {
    for (const t of CONFIG.times) {
      slots.push(d.value + ' ' + t);
    }
  }

  // CSV headers
  const teamRows  = [['Team', 'Poule', 'player_1', 'tel_player_1', 'player_2', 'tel_player_2']];
  const availRows = [['Team', ...slots]];

  for (const response of responses) {
    const items = response.getItemResponses();

    let team = '', poule = '', p1 = '', tel1 = '', p2 = '', tel2 = '';
    let availGrid = null;  // String[][] from checkbox grid

    for (const item of items) {
      const title = item.getItem().getTitle();
      const val   = item.getResponse();
      switch (title) {
        case 'Teamnaam':                   team      = val; break;
        case 'Poule':                      poule     = val; break;
        case 'Naam speler 1':              p1        = val; break;
        case 'Telefoonnummer speler 1':    tel1      = val; break;
        case 'Naam speler 2':              p2        = val; break;
        case 'Telefoonnummer speler 2':    tel2      = val; break;
        case 'Op welke data en tijdstippen is jouw team beschikbaar?':
          availGrid = val;  // 2D: availGrid[dateIndex] = [checkedTime, ...]
          break;
      }
    }

    teamRows.push([team, poule, p1, tel1, p2, tel2]);

    // One column per slot: TRUE if that (date, time) was checked, empty otherwise
    const availRow = [team];
    for (let s = 0; s < slots.length; s++) {
      const dateIdx = Math.floor(s / CONFIG.times.length);
      const time    = CONFIG.times[s % CONFIG.times.length];
      const checked = availGrid &&
                      availGrid[dateIdx] &&
                      availGrid[dateIdx].includes(time);
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

/**
 * TC Kooike — Poulecompetitie: Google Form creator & CSV exporter
 * ================================================================
 * HOW TO USE
 * ----------
 * 1. Go to https://script.google.com and create a new project.
 * 2. Paste this entire file into the editor.
 * 3. Edit the CONFIGURATION section below (dates, times, poules).
 * 4. Run createForm() → a Google Form is created in your Drive.
 * 5. Share the form link with all team captains.
 * 6. After collecting responses, run exportToCSV().
 *    Two files appear in your Google Drive root:
 *      - teams.csv            → use with --teams
 *      - team_availabilities.csv → use with --avail
 */


// ══════════════════════════════════════════════════════════════════
//  CONFIGURATION  — edit this block before running
// ══════════════════════════════════════════════════════════════════

const CONFIG = {
  formTitle: 'TC Kooike – Poulecompetitie 2026: Teamgegevens & Beschikbaarheid',

  // Poule identifiers shown in the dropdown
  poules: ['A', 'B', 'C'],

  // Match dates — add/remove rows as needed.
  // label : shown to respondents in the form
  // value : must be YYYY-MM-DD (used in the exported CSV)
  dates: [
    { label: 'ma 4 mei 2026',   value: '2026-05-04' },
    { label: 'ma 11 mei 2026',  value: '2026-05-11' },
    { label: 'ma 18 mei 2026',  value: '2026-05-18' },
    { label: 'ma 25 mei 2026',  value: '2026-05-25' },
    { label: 'ma 1 jun 2026',   value: '2026-06-01' },
    { label: 'ma 8 jun 2026',   value: '2026-06-08' },
  ],

  // Available time slots — must be HH:MM (used in the exported CSV)
  times: ['18:00', '19:30', '21:00'],
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
    .setTitle('Op welke data en tijdstippen ben jij beschikbaar?')
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

  // Build the full list of slot column headers: ['2026-05-04 18:00', ...]
  const slots = [];
  for (const d of CONFIG.dates) {
    for (const t of CONFIG.times) {
      slots.push(d.value + ' ' + t);
    }
  }

  // CSV headers
  const teamRows   = [['Team', 'Poule', 'player_1', 'tel_player_1', 'player_2', 'tel_player_2']];
  const availRows  = [['Team', ...slots]];

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
        case 'Op welke data en tijdstippen ben jij beschikbaar?':
          availGrid = val;   // 2D: availGrid[dateIndex] = [selectedTime, ...]
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
  writeCSV(folder, 'teams.csv',                teamRows);
  writeCSV(folder, 'team_availabilities.csv',  availRows);

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
      // Quote cells that contain commas, quotes, or newlines
      return (s.includes(',') || s.includes('"') || s.includes('\n'))
        ? '"' + s.replace(/"/g, '""') + '"'
        : s;
    }).join(',')
  ).join('\n');

  // Delete existing file with the same name to avoid duplicates
  const existing = folder.getFilesByName(filename);
  while (existing.hasNext()) existing.next().setTrashed(true);

  folder.createFile(filename, csv, MimeType.PLAIN_TEXT);
  Logger.log('Wrote ' + filename + ' (' + (rows.length - 1) + ' rows)');
}

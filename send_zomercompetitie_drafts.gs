/**
 * TC Kooike — Zomercompetitie: bulk-send prepared Gmail drafts
 * ================================================================
 * HOW TO USE
 * ----------
 * 1. Go to https://script.google.com and create a new project
 *    (use the SAME Google account that has the drafts, i.e. the
 *    Gmail account these were drafted into).
 * 2. Paste this entire file into the editor.
 * 3. Run previewZomercompetitieDrafts() first — authorize Gmail
 *    access when asked. Check the Execution log (View → Logs) to
 *    see exactly which drafts WOULD be sent. Nothing is sent yet.
 * 4. Once the preview looks right, run sendZomercompetitieDrafts()
 *    to actually send them.
 *
 * SAFETY
 * ------
 * Only drafts whose subject matches SUBJECT_FILTER are touched — any
 * unrelated draft sitting in your account is left alone.
 */

const SUBJECT_FILTER = 'Zomercompetitie TC Kooike';

function previewZomercompetitieDrafts() {
  run_(false);
}

function sendZomercompetitieDrafts() {
  run_(true);
}

function run_(reallySend) {
  const drafts = GmailApp.getDrafts();
  let matched = 0;
  let sent = 0;

  drafts.forEach(draft => {
    const msg = draft.getMessage();
    const subject = msg.getSubject();
    if (subject.indexOf(SUBJECT_FILTER) === -1) {
      return;
    }
    matched++;
    const to = msg.getTo();

    if (!reallySend) {
      Logger.log('[PREVIEW] would send to %s — subject: %s', to, subject);
      return;
    }

    draft.send();
    sent++;
    Logger.log('Sent to %s — subject: %s', to, subject);
  });

  Logger.log('---');
  Logger.log('%s draft(s) matched "%s".', matched, SUBJECT_FILTER);
  Logger.log(reallySend ? '%s draft(s) sent.' : 'Preview only — nothing was sent.', sent);
}

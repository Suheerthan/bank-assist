# Changelog

## v1.1 (6 Oct 2026)

**Verification**
- Added a held-out set of 20 new wordings (`data/messages_unseen.json`). The verification tab, `python -m eval.evaluate` and `eval/report.md` now show the development and held-out scores side by side.
- The first held-out run exposed overfitting: intent 65%, urgent cases caught 28.6%. After the fixes below: intent 95%, FAQ top-1 90%, urgent cases caught 100%, escalation precision 100%.

**Escalation**
- Escalation scenarios moved from code to `data/escalation_rules.json` ("configured escalation scenarios"). Each rule has a team, a level, the intent it implies and its approved FAQ.
- Broader patterns for card loss (snatched, pickpocketed, left my card), unrecognised debits, remote-access-app scams, "tracking says delivered" and address changes the customer did not make.
- When a rule fires, its linked FAQ is used for the draft (marked "chosen by escalation rule").

**Safety**
- New compliance and grounding gate (`app/compliance.py`, `POST /api/check`). Checks drafts and the agent's live edits for secret requests, promises, unmasked personal data, links, financial advice and figures not in the FAQ.
- AI drafts that fail the gate are replaced by the template.
- Saving a flagged reply needs a second click; flags are stored with the record and counted in the History tab.
- Broader out-of-scope rules for balance questions and investment advice.

**Agent experience**
- Multi-issue detection: "the customer also mentions..." note when a message raises a second request.
- CSV export of saved interactions (History tab, `GET /api/interactions.csv`).
- Sample dropdown now includes the held-out messages.

**Tests and docs**
- 25 tests (18 unit, 7 Playwright), up from 15.
- Updated README, architecture diagram and decisions, demo script, prompts log, sample output, two new screenshots.

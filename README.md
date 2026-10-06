# Banking Customer Service Interaction Assistant

TCS Technology Day Hackathon, Use Case 6. An agent-assist tool for a fictional bank (Lotus Harbour Bank). A service agent pastes a customer message; the assistant detects the intent, finds the approved FAQ, drafts a policy-grounded reply, flags card-loss and fraud cases for immediate human hand-off, and writes an interaction summary. The agent reviews and edits everything. Nothing is sent to a customer automatically.

All data is synthetic. The assistant handles informational requests only: no authentication, transactions, balance access or financial advice.

![Architecture](docs/architecture.png)

## Quick start (Windows, about 5 minutes)

You need Python 3.13. MongoDB is optional (the app uses a local file if MongoDB is not running).

```powershell
cd bank-assist
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Or just double-click `run.bat`, which does all of the above.

macOS/Linux: use `python3.13 -m venv .venv` and `source .venv/bin/activate`.

### Turning on the AI model (optional)

The app works fully offline with rules and templates. To let an LLM classify intent and write the drafts and summaries, edit `.env`:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
```

or `LLM_PROVIDER=anthropic` with `ANTHROPIC_API_KEY`. Model names are set in `.env` too (default `gemini-3.8-flash`; Gemini 2.5 models return 404 for new projects). Check the provider's current model list if a call fails. If the AI call fails for any reason (no internet, quota, wrong key), the app silently falls back to rules and templates and keeps working. The status line at the top right shows which engine is active.

## How each expected outcome is met

| Expected outcome (6.4) | Where it happens |
|---|---|
| 1. Detect service intent and request details | `app/knowledge.py` classifier with confidence and rationale; `app/extract.py` pulls amount, UTR, channel, timing, card |
| 2. Retrieve the most applicable approved FAQ | BM25 retrieval over `data/faqs.json`, top 3 shown with match scores; weak matches return "no reliable match" instead of guessing |
| 3. Editable, policy-grounded response with next steps | Draft built only from the retrieved FAQ; agent edits it in the console; next steps and documents listed from the FAQ |
| 4. Flag card loss, fraud and other escalations | Configured scenarios in `data/escalation_rules.json` (5 rules: card loss, unauthorised transaction, credentials shared, delivered-not-received, address changed without request), evaluated by `app/escalation.py`; red hand-off banner shows the rule, the team and the phrase that triggered it. Add a scenario by editing the JSON, no code change |
| 5. Interaction summary for review and records | Generated on "Approve and save", stored in MongoDB with whether the agent edited the draft and any compliance flags; exportable as CSV |
| Bonus 6.5: tone options | Concise, standard and empathetic. Tone changes the wording only; the FAQ guidance text is identical in all three (unit-tested) |

### Value-added features (beyond the use case)

1. **PII shield.** Card numbers, account numbers, phone numbers and emails are masked before analysis, storage or any AI call.
2. **Customer mood meter.** Detects distress signals ("scared", "no refund yet") and suggests the empathetic tone.
3. **Clarifying question.** Asks for the UTR on failed transfers, or the amount and date on fraud reports, when they are missing.
4. **Out-of-scope guard.** Balance requests, transfer requests, investment advice and PIN resets get a safe hand-off reply instead of an answer.
5. **Built-in verification tab.** Runs all 55 labelled messages (development + held-out) through the live pipeline and shows accuracy in the UI.
6. **Source feedback and analytics.** Helpful / not helpful on each FAQ source, and a History tab with escalation and edit counts.
7. **Works offline.** The full flow runs without any API key, so the demo cannot be broken by Wi-Fi.
8. **Compliance and grounding gate (new in v1.1).** Every draft, and the agent's edits as they type, are checked for: asking for an OTP/PIN/CVV/password, promising an outcome or claiming an action was taken, unmasked personal data, links, financial advice, and any figure (days, hours, fees, %) that is not in the approved FAQ. An AI draft that fails is thrown away and the FAQ template is used instead. If the agent saves a flagged reply, they must confirm, and the flags are stored with the record.
9. **Multi-issue detection (new in v1.1).** If a customer raises two things ("my UPI failed, and I also need a statement"), the console handles the main one and shows "the customer also mentions..." so the second issue is not lost.
10. **Held-out verification (new in v1.1).** A second labelled set of 20 new wordings (`data/messages_unseen.json`) measures how well the rules generalise, shown next to the development-set score.
11. **CSV export (new in v1.1).** One click in the History tab downloads all saved interactions for record keeping.

## User manual (for the service agent)

1. **Enter the message.** Paste what the customer wrote into *Message text*, or choose one from *Load a synthetic message*. Press *Analyse message* (or Ctrl+Enter).
2. **Check for the red banner.** If a red band appears at the top, this is a card-loss or fraud case. Hand the customer to the named team immediately. The save button changes to *Approve, save and hand off*.
3. **Read the analysis (right column).** The intent, how confident the assistant is and why, the three closest approved FAQs (the one used for the draft is outlined), and your next steps as a checklist. Mark FAQs *Helpful* or *Not helpful* to improve the knowledge base.
   If an amber note says *The customer also mentions...*, deal with that second request after this one.
4. **Review the draft (middle column).** Switch tone if needed. Edit the text freely. If an amber note says there is no reliable FAQ match, do not improvise; ask the suggested clarifying question instead.
5. **Watch the compliance panel under the draft.** Green means the reply is safe. Red lists exactly what to fix (for example "Asks the customer for their OTP" or "Quotes figures not found in the approved FAQ: 2 hours"). It updates as you type.
6. **Approve and save.** The final reply, your notes and an auto-generated summary are saved. If the compliance panel is red, the button asks you to confirm and the flags are recorded. Use *Copy reply* to paste the text into your channel.
7. **History tab.** All saved interactions with summaries, escalation count, edit count and compliance flags. *Export CSV* downloads them.
8. **Verification tab.** Press *Run verification* to measure accuracy on the development set and the held-out set.

## Verification

```powershell
python -m eval.evaluate          # accuracy report -> eval/report.md
pytest tests/test_core.py        # 18 unit tests
pytest tests/e2e                 # 7 Playwright browser tests (starts its own server)
pytest                           # everything
```

Current results (offline mode):

| Metric | Development set (35) | Held-out set (20) |
|---|---|---|
| Intent accuracy | 100% | 95% |
| FAQ top-1 accuracy | 97.1% | 90% |
| FAQ top-3 recall | 100% | 95% |
| Urgent cases caught | 100% | 100% |
| Escalation precision | 100% | 100% |
| Drafts passing the compliance check | 100% | 100% |

The development set is what the keywords were tuned on. The held-out set was written afterwards with new wording. Its first run scored only 65% intent accuracy and caught 28.6% of urgent cases ("purse got snatched", "debit alert I don't recognise"). That finding drove the v1.1 changes: broader, configurable escalation rules and rule-linked FAQs. See `eval/report.md` for the before/after table and every case. Remaining misses: UNS-11 (an attested statement "for my education loan" is pulled towards the loan FAQ) and UNS-15 (a remote-access-app scam that also mentions missing money gets the unauthorised-transaction FAQ instead of the phishing FAQ; it is still escalated).

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Engine, storage backend, FAQ count |
| GET | `/api/samples` | Labelled synthetic messages |
| GET | `/api/faqs` | Approved FAQ knowledge base |
| POST | `/api/analyze` | `{message, tone?}` → full analysis and draft |
| POST | `/api/draft` | Re-draft in another tone, same guidance |
| POST | `/api/check` | Compliance and grounding check on an edited reply |
| POST | `/api/interactions` | Save approved reply, notes and summary |
| GET | `/api/interactions` | Saved interactions, newest first |
| GET | `/api/interactions.csv` | Download saved interactions as CSV |
| POST | `/api/feedback` | Helpful / not helpful on a source |
| GET | `/api/stats` | Counts for the History tab |
| POST | `/api/evaluate` | Run verification |

Interactive API docs: http://127.0.0.1:8000/docs

## Project structure

```
app/            FastAPI app and pipeline (config, extract, escalation, knowledge, llm, pipeline, compliance, storage, evaluation)
data/           faqs.json (15 FAQs), messages.json (30 + 5 labelled), messages_unseen.json (20 held-out), escalation_rules.json
prompts/        The three prompts sent to the AI model
static/         Agent console (HTML, CSS, JS)
eval/           Verification script and report
tests/          Unit tests and Playwright E2E tests
docs/           Architecture diagram, prompts log, demo script, screenshots, sample output
```

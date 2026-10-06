# Prompts used

## 1. Prompts inside the application (`prompts/`)

| File | Used for | Guardrails written into the prompt |
|---|---|---|
| `classify_intent.txt` | Intent classification when an LLM is enabled | Fixed intent list, out-of-scope definition, "extract only details literally present", JSON-only output |
| `draft_response.txt` | Drafting the customer reply | Use only the approved FAQ; no new fees, timelines, links or promises; never ask for OTP/PIN/CVV; no financial advice; never claim an action was already taken; tone instruction; escalation instruction |
| `summarize_interaction.txt` | Interaction summary after approval | Factual and neutral, no personal data, no invented facts |

Every LLM output is validated (intent must be in the allowed list, JSON must parse). If validation fails, the rule engine result is used and the rationale says so.

AI drafts also pass through the compliance and grounding gate (`app/compliance.py`): if the draft asks for a secret, promises an outcome, contains personal data or advice, or quotes any figure that is not in the approved FAQ, it is discarded and the FAQ template is used. The console says "AI draft failed the grounding check" so the agent knows.

## 2. Prompts used during development (AI in the SDLC)

Fill this in as you work. Judges score "AI usage in development" and "prompts used".

| Phase | Tool | Prompt (short) | What it produced |
|---|---|---|---|
| Requirements | Claude | "Compare use cases 5 and 6 for a 6-hour build; which scores better on the evaluation criteria?" | Use case choice and scope |
| Design | Claude | "Design an agent-assist architecture for use case 6 with deterministic escalation and an offline fallback" | Architecture, pipeline steps |
| Synthetic data | Claude | "Generate 30 fictional bank customer messages across these 7 intents with expected intent, FAQ and escalation labels" | `data/messages.json` |
| Synthetic data | Claude | "Write 12-15 fictional bank FAQs with intent, eligibility, steps, documents and escalation condition" | `data/faqs.json` |
| Code | Claude Code / Copilot | "Build a FastAPI endpoint that ..." | `app/` modules |
| Testing | Claude Code | "Write Playwright tests that check the fraud banner, tone switch and save flow" | `tests/e2e/` |
| Docs | Claude | "Write a user manual for a bank service agent using this console" | `README.md` |
| Verification | Claude (Cowork) | "Write 20 new customer messages in different wording from the development set, with labels, to test generalisation" | `data/messages_unseen.json`; exposed overfitted escalation rules |
| Upgrade | Claude (Cowork) | "Review the project against the evaluation criteria and upgrade it: configurable escalation rules, a compliance gate on drafts and edits, multi-issue detection, CSV export, tests and docs" | v1.1 changes, `app/compliance.py`, 10 new tests |
| (add yours) | | | |

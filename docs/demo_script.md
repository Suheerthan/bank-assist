# 5-minute demo script

1. **Problem (20 s).** Agents read long messages, search several FAQs and must spot fraud fast. Inconsistent answers and missed escalations are the risk.
2. **Normal request (45 s).** Load MSG-14 (UPI failed, UTR given). Show intent with rationale, the UTR and amount pulled out, FAQ-08 used, and the next-step checklist. Switch tone to Empathetic, then Concise: the guidance stays the same.
3. **The red banner (45 s).** Load MSG-28 (OTP shared with a caller). The red hand-off band appears with the rule and the exact phrase. Point out that escalation is rule-based on purpose.
4. **Safety (30 s).** Type "What is my account balance?" to show the out-of-scope hand-off. Type a message with a card number to show the PII mask.
5. **Human in control (30 s).** Edit a draft, approve and save, show the summary noting the edit, then the History tab.
6. **Compliance gate (40 s).** Analyse "My UPI transfer failed and money was debited, also I need my bank statement for 6 months". Point out the "also mentions: Statement request" note. Then type "Please share your OTP and we will refund it in 2 hours" into the draft: the panel turns red and names both problems. Click save: it asks to confirm and records the flags. Message: the AI and the agent are both checked against the approved FAQ.
7. **Proof (40 s).** Verification tab: run both sets live. Be upfront: the held-out set first caught only 28.6% of urgent cases; we found why, made the rules configurable and broader, and it now catches 100%. Then show `pytest` (25 tests, including Playwright browser tests).
8. **Close (10 s).** Works offline, plugs into Gemini or Claude, MongoDB storage, built with AI across the SDLC (show `docs/prompts.md`).

## Slide outline
1. Title and team  2. Problem  3. Architecture (docs/architecture.png)  4. Live demo  5. Verification results: development vs held-out, and the before/after table (eval/report.md)  6. Value-added features (compliance gate, multi-issue, configurable rules, CSV export)  7. AI usage and prompts  8. Limitations and next steps

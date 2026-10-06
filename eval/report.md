# Verification report

Offline mode (rules + templates). Regenerate with `python -m eval.evaluate`.

- **Development set**: 30 use-case messages + 5 extra (loan, out-of-scope). Keywords were tuned on these.
- **Held-out set**: 20 new wordings written after the rules were built, to measure generalisation.

| Metric | Development set | Held-out set |
|---|---|---|
| Labelled cases | 35 | 20 |
| Intent accuracy | 100.0% | 95.0% |
| FAQ top-1 accuracy | 97.1% | 90.0% |
| FAQ top-3 recall | 100.0% | 95.0% |
| Escalation recall (urgent cases caught) | 100.0% | 100.0% |
| Escalation precision | 100.0% | 100.0% |
| Drafts passing the compliance check | 100.0% | 100.0% |
| Average latency | 1.2 ms | 0.8 ms |

## What the held-out set taught us

The first run of the held-out set (before v1.1) exposed that the rules were overfitted to the development wording:

| Held-out metric | First run (v1.0) | Now (v1.1) |
|---|---|---|
| Intent accuracy | 65.0% | 95.0% |
| FAQ top-1 accuracy | 55.0% | 90.0% |
| Urgent cases caught | 28.6% | 100.0% |

Missed urgent cases were phrased in ways the rules had not seen ("purse got snatched", "left my card at the restaurant", "debit alert I don't recognise", "caller asked me to install an app"). We broadened the escalation lexicon with general synonyms (not the exact test sentences), moved the rules into `data/escalation_rules.json`, and let each rule name its approved FAQ. Because the held-out set has now been looked at once, it is no longer fully blind: add fresh messages to `data/messages_unseen.json` for the next honest score.

## Intent errors

- [unseen] statement_request -> loan_documents: 1

## Case by case

| Set | ID | Expected intent | Predicted | FAQ expected | FAQ predicted | Escalation | Result |
|---|---|---|---|---|---|---|---|
| tuned | MSG-01 | card_delivery | card_delivery | FAQ-01 | FAQ-01 | no | pass |
| tuned | MSG-02 | card_delivery | card_delivery | FAQ-01 | FAQ-01 | no | pass |
| tuned | MSG-03 | card_delivery | card_delivery | FAQ-02 | FAQ-02 | no | pass |
| tuned | MSG-04 | card_delivery | card_delivery | FAQ-02 | FAQ-02 | no | pass |
| tuned | MSG-05 | fee_explanation | fee_explanation | FAQ-03 | FAQ-03 | no | pass |
| tuned | MSG-06 | fee_explanation | fee_explanation | FAQ-03 | FAQ-03 | no | pass |
| tuned | MSG-07 | fee_explanation | fee_explanation | FAQ-04 | FAQ-04 | no | pass |
| tuned | MSG-08 | fee_explanation | fee_explanation | FAQ-04 | FAQ-04 | no | pass |
| tuned | MSG-09 | fee_explanation | fee_explanation | FAQ-05 | FAQ-05 | no | pass |
| tuned | MSG-10 | address_update | address_update | FAQ-06 | FAQ-06 | no | pass |
| tuned | MSG-11 | address_update | address_update | FAQ-06 | FAQ-06 | no | pass |
| tuned | MSG-12 | address_update | address_update | FAQ-07 | FAQ-07 | no | pass |
| tuned | MSG-13 | address_update | address_update | FAQ-07 | FAQ-06 | no | CHECK |
| tuned | MSG-14 | failed_transfer | failed_transfer | FAQ-08 | FAQ-08 | no | pass |
| tuned | MSG-15 | failed_transfer | failed_transfer | FAQ-08 | FAQ-08 | no | pass |
| tuned | MSG-16 | failed_transfer | failed_transfer | FAQ-08 | FAQ-08 | no | pass |
| tuned | MSG-17 | failed_transfer | failed_transfer | FAQ-09 | FAQ-09 | no | pass |
| tuned | MSG-18 | statement_request | statement_request | FAQ-10 | FAQ-10 | no | pass |
| tuned | MSG-19 | statement_request | statement_request | FAQ-10 | FAQ-10 | no | pass |
| tuned | MSG-20 | statement_request | statement_request | FAQ-11 | FAQ-11 | no | pass |
| tuned | MSG-21 | statement_request | statement_request | FAQ-11 | FAQ-11 | no | pass |
| tuned | MSG-22 | card_loss | card_loss | FAQ-12 | FAQ-12 | yes | pass |
| tuned | MSG-23 | card_loss | card_loss | FAQ-12 | FAQ-12 | yes | pass |
| tuned | MSG-24 | card_loss | card_loss | FAQ-12 | FAQ-12 | yes | pass |
| tuned | MSG-25 | card_loss | card_loss | FAQ-12 | FAQ-12 | yes | pass |
| tuned | MSG-26 | suspected_fraud | suspected_fraud | FAQ-13 | FAQ-13 | yes | pass |
| tuned | MSG-27 | suspected_fraud | suspected_fraud | FAQ-13 | FAQ-13 | yes | pass |
| tuned | MSG-28 | suspected_fraud | suspected_fraud | FAQ-14 | FAQ-14 | yes | pass |
| tuned | MSG-29 | suspected_fraud | suspected_fraud | FAQ-14 | FAQ-14 | yes | pass |
| tuned | MSG-30 | suspected_fraud | suspected_fraud | FAQ-13 | FAQ-13 | yes | pass |
| tuned | EXT-01 | loan_documents | loan_documents | FAQ-15 | FAQ-15 | no | pass |
| tuned | EXT-02 | loan_documents | loan_documents | FAQ-15 | FAQ-15 | no | pass |
| tuned | EXT-03 | out_of_scope | out_of_scope | - | - | no | pass |
| tuned | EXT-04 | out_of_scope | out_of_scope | - | - | no | pass |
| tuned | EXT-05 | out_of_scope | out_of_scope | - | - | no | pass |
| unseen | UNS-01 | card_delivery | card_delivery | FAQ-01 | FAQ-01 | no | pass |
| unseen | UNS-02 | card_delivery | card_delivery | FAQ-02 | FAQ-02 | yes | pass |
| unseen | UNS-03 | fee_explanation | fee_explanation | FAQ-03 | FAQ-03 | no | pass |
| unseen | UNS-04 | fee_explanation | fee_explanation | FAQ-04 | FAQ-04 | no | pass |
| unseen | UNS-05 | fee_explanation | fee_explanation | FAQ-05 | FAQ-05 | no | pass |
| unseen | UNS-06 | address_update | address_update | FAQ-06 | FAQ-06 | no | pass |
| unseen | UNS-07 | address_update | address_update | FAQ-06 | FAQ-06 | yes | pass |
| unseen | UNS-08 | failed_transfer | failed_transfer | FAQ-08 | FAQ-08 | no | pass |
| unseen | UNS-09 | failed_transfer | failed_transfer | FAQ-09 | FAQ-09 | no | pass |
| unseen | UNS-10 | statement_request | statement_request | FAQ-10 | FAQ-10 | no | pass |
| unseen | UNS-11 | statement_request | loan_documents | FAQ-11 | FAQ-15 | no | CHECK |
| unseen | UNS-12 | card_loss | card_loss | FAQ-12 | FAQ-12 | yes | pass |
| unseen | UNS-13 | card_loss | card_loss | FAQ-12 | FAQ-12 | yes | pass |
| unseen | UNS-14 | suspected_fraud | suspected_fraud | FAQ-13 | FAQ-13 | yes | pass |
| unseen | UNS-15 | suspected_fraud | suspected_fraud | FAQ-14 | FAQ-13 | yes | CHECK |
| unseen | UNS-16 | suspected_fraud | suspected_fraud | FAQ-14 | FAQ-14 | yes | pass |
| unseen | UNS-17 | loan_documents | loan_documents | FAQ-15 | FAQ-15 | no | pass |
| unseen | UNS-18 | out_of_scope | out_of_scope | - | - | no | pass |
| unseen | UNS-19 | out_of_scope | out_of_scope | - | - | no | pass |
| unseen | UNS-20 | out_of_scope | out_of_scope | - | - | no | pass |

"""Unit tests for the deterministic parts: masking, extraction, escalation, scope, retrieval, tone."""
import os

os.environ["LLM_PROVIDER"] = "none"

from app.escalation import check_escalation  # noqa: E402
from app.extract import extract_details, mask_pii  # noqa: E402
from app.pipeline import analyze  # noqa: E402


def test_card_number_is_masked_but_utr_is_kept():
    masked, kinds = mask_pii("Card 4000 1234 5678 9010 used, UTR 412398765432")
    assert "4000 1234" not in masked and "XXXX XXXX XXXX 9010" in masked
    assert "412398765432" in masked
    assert kinds == ["card number"]


def test_phone_and_email_are_masked():
    masked, kinds = mask_pii("call 9876543210 or mail priya.k@example.com")
    assert "9876543210" not in masked and "example.com" in masked and "priya" not in masked
    assert set(kinds) == {"phone number", "email"}


def test_details_extraction():
    d = extract_details("I sent Rs 5,000 by UPI yesterday. UTR 412398765432")
    assert d["amounts_inr"] == ["5000"]
    assert "412398765432" in d["reference_numbers"]
    assert d["channel"] == ["UPI"] and "yesterday" in d["timing"]


def test_card_loss_and_fraud_always_escalate():
    for text in ["I lost my debit card", "There is a payment I did not make", "I shared the OTP with a caller"]:
        r = analyze(text)
        assert r["escalation"]["escalate"] and r["escalation"]["level"] == "critical", text


def test_informational_request_does_not_escalate():
    assert not check_escalation("How do I download my statement?")["escalate"]


def test_out_of_scope_requests_get_safe_handoff():
    for text in ["What is my account balance?", "Should I invest in mutual funds?", "Please transfer 2000 rupees to my mother"]:
        r = analyze(text)
        assert r["intent"] == "out_of_scope" and r["faq"] is None, text


def test_no_reliable_match_does_not_improvise():
    r = analyze("hello")
    assert r["faq"] is None and r["no_match_reason"] and r["clarifying_question"]


def test_tone_changes_wording_not_guidance():
    drafts = {t: analyze("UPI failed but money debited", tone=t)["draft"] for t in ("concise", "standard", "empathetic")}
    key_fact = "UPI and IMPS reversals normally complete within 1 working day"
    assert all(key_fact in d for d in drafts.values())
    assert len(set(drafts.values())) == 3


def test_failed_transfer_without_reference_asks_for_it():
    r = analyze("My NEFT transfer failed and money was deducted")
    assert r["intent"] == "failed_transfer" and "UTR" in r["clarifying_question"]


def test_labelled_set_meets_targets():
    from app.evaluation import run_evaluation
    m = run_evaluation()["metrics"]
    assert m["intent_accuracy"] >= 90
    assert m["escalation_recall"] == 100  # never miss an urgent case


# ---------- v1.1 upgrades ----------

def test_escalation_rules_are_configuration():
    from app.escalation import ESCALATION_RULES, RULES_FILE
    assert RULES_FILE.name == "escalation_rules.json"
    assert {"Card lost or stolen", "Unauthorised transaction"} <= {r["rule"] for r in ESCALATION_RULES}


def test_new_wordings_of_urgent_cases_escalate():
    for text in ["my purse got snatched with my debit card in it",
                 "I got a debit alert I don't recognise",
                 "A caller told me to install an app and now money is missing"]:
        assert analyze(text)["escalation"]["level"] == "critical", text


def test_rule_pins_its_approved_faq():
    r = analyze("Tracking says delivered but I never got the card")
    assert r["escalation"]["escalate"] and r["faq"]["id"] == "FAQ-02"


def test_multi_issue_message_reports_second_intent():
    r = analyze("My UPI transfer failed and money was debited, also I need my bank statement for 6 months")
    assert r["intent"] == "failed_transfer"
    assert r["secondary_intent"]["intent"] == "statement_request"


def test_compliance_flags_unsafe_edits():
    from app.compliance import check_reply
    from app.pipeline import KB
    faq = KB.by_id["FAQ-08"]
    assert check_reply("Please share your OTP so we can verify.", faq)["status"] == "block"
    assert check_reply("Never share your OTP with anyone.", faq)["status"] == "pass"
    assert check_reply("We have already refunded the amount.", faq)["status"] == "block"
    assert check_reply("The reversal happens in 2 hours.", faq)["status"] == "block"   # figure not in FAQ
    assert check_reply("Card 4000 1234 5678 9010 is fine.", faq)["status"] == "block"  # unmasked card


def test_every_template_draft_passes_compliance():
    import json
    from app.config import DATA_DIR
    for name in ("messages.json", "messages_unseen.json"):
        for c in json.loads((DATA_DIR / name).read_text(encoding="utf-8")):
            for tone in ("concise", "standard", "empathetic"):
                assert analyze(c["text"], tone=tone)["compliance"]["status"] == "pass", (c["id"], tone)


def test_ungrounded_ai_draft_is_replaced_by_template(monkeypatch):
    from app import llm, pipeline
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "Your money is guaranteed back in 2 hours.")
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: None)
    r = pipeline.analyze("UPI failed but money debited", tone="standard")
    assert r["draft_source"] == "template:grounding"
    assert "guaranteed" not in r["draft"] and r["compliance"]["status"] == "pass"


def test_held_out_set_meets_targets():
    from app.evaluation import run_evaluation
    unseen = run_evaluation()["sets"]["unseen"]
    assert unseen["escalation_recall"] == 100
    assert unseen["intent_accuracy"] >= 85

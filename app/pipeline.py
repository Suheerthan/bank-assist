"""Agent-assist pipeline: mask -> extract -> classify -> escalate -> retrieve -> draft -> summarise."""
import re
import time
import uuid
from datetime import datetime, timezone

from . import config, llm
from .compliance import check_reply
from .escalation import check_escalation, distress_meter
from .extract import extract_details, mask_pii
from .knowledge import INTENTS, OUT_OF_SCOPE_RULES, KnowledgeBase

KB = KnowledgeBase.load()
VALID_INTENTS = set(INTENTS) | {"unclear"}
TONES = {
    "concise": "Concise: 2-3 short sentences, only the essential guidance.",
    "standard": "Standard: polite and clear, a short explanation followed by what to do.",
    "empathetic": "Highly empathetic: acknowledge how the customer feels first, then the same guidance, with reassurance.",
}

ACKNOWLEDGE = {
    "card_delivery": "I understand waiting for a card can be frustrating.",
    "fee_explanation": "I understand it is worrying to see an unexpected charge.",
    "address_update": "Thank you for letting us know about your move.",
    "failed_transfer": "I understand how stressful it is when money leaves your account but does not reach the person.",
    "statement_request": "Happy to help you get your statement.",
    "card_loss": "I'm sorry you've lost your card. Let's make sure it's protected right away.",
    "suspected_fraud": "I'm really sorry this has happened. You did the right thing by contacting us straight away.",
    "loan_documents": "Thank you for following up on your loan application.",
}

HANDOFF_TEXT = {
    "Balance enquiry needs authenticated access": "For your security, balances can only be shared after you log in to the mobile app or net banking, or at a branch after verification.",
    "Financial or investment advice is not provided": "I'm not able to give investment or financial advice. A relationship manager at your branch can walk you through the available products.",
    "Assistant cannot perform transactions": "I'm not able to make transactions on your behalf. You can make this transfer yourself securely in the mobile app or net banking.",
    "Login, password or PIN reset needs authentication": "Password and PIN resets need identity verification, which you can complete in the mobile app or at a branch.",
}


def _greeting(tone: str) -> str:
    return "" if tone == "concise" else "Hello,\n\n"


def _closing(tone: str) -> str:
    return {
        "concise": "",
        "standard": "\n\nPlease let us know if you need anything else.",
        "empathetic": "\n\nWe're here to help, and we'll keep you updated until this is sorted.",
    }[tone]


def template_reply(intent: str, faq: dict | None, tone: str, escalation: dict, handoff: str | None) -> str:
    if intent == "out_of_scope":
        text = handoff or "This request needs to be handled by a team member after verification."
        return _greeting(tone) + text + _closing(tone)
    if not faq:
        return (_greeting(tone) + "Thanks for reaching out. Could you share a little more detail, such as whether this is about a card, "
                "a transfer, a charge, your address or a statement, so we can guide you correctly?" + _closing(tone))
    parts = []
    if tone == "empathetic" and intent in ACKNOWLEDGE:
        parts.append(ACKNOWLEDGE[intent])
    if escalation["escalate"]:
        team = escalation["reasons"][0]["team"].lower()
        parts.append(f"Because this needs urgent attention, I'm connecting you with our {team} now.")
    # Tone changes wording around the guidance, never the guidance itself
    parts.append(faq["answer"])
    body = " ".join(parts)
    docs = faq.get("required_documents") or []
    if docs and tone != "concise":
        body += "\n\nPlease keep these ready:\n" + "\n".join(f"- {d}" for d in docs)
    elif docs:
        body += " You'll need: " + "; ".join(docs) + "."
    return _greeting(tone) + body + _closing(tone)


def llm_reply(masked: str, faq: dict, tone: str, escalation: dict) -> str | None:
    esc = ""
    if escalation["escalate"]:
        esc = (f"ESCALATION: this case is being handed to the {escalation['reasons'][0]['team']}. "
               "Tell the customer you are connecting them to that team now and keep the reply short and calm.")
    prompt = llm.load_prompt("draft_response").format(
        bank_name=config.BANK_NAME, faq_id=faq["id"], faq_title=faq["title"], faq_answer=faq["answer"],
        faq_steps="\n".join(f"- {s}" for s in faq["steps"]),
        faq_documents=", ".join(faq["required_documents"]) or "none",
        message=masked, tone_instruction=TONES[tone], escalation_instruction=esc,
    )
    return llm.complete(prompt)


def classify(masked: str) -> dict:
    rule_result = KB.classify(masked)
    if not llm.enabled():
        return rule_result
    intent_list = "\n".join(f"- {k}: {v}" for k, v in INTENTS.items())
    data = llm.complete_json(llm.load_prompt("classify_intent").format(intent_list=intent_list, message=masked))
    if not data or data.get("intent") not in VALID_INTENTS:
        rule_result["rationale"] += " (LLM unavailable, rules used.)"
        return rule_result
    agree = data["intent"] == rule_result["intent"]
    return {
        "intent": data["intent"],
        "confidence": round(float(data.get("confidence", 0.7)), 2),
        "rationale": f"{data.get('rationale', '').strip()} Rule engine {'agrees' if agree else 'suggested ' + INTENTS.get(rule_result['intent'], rule_result['intent'])}.",
        "scores": rule_result.get("scores", {}),
        "method": "llm+rules",
        "rules_agree": agree,
        "secondary": rule_result.get("secondary"),
    }


def draft(masked: str, intent: str, faq_id: str | None, tone: str, escalation: dict) -> tuple[str, str]:
    """Returns (reply, source). Source is "llm", "template", or "template:grounding" when an AI draft
    was rejected by the grounding check and replaced by the FAQ template."""
    tone = tone if tone in TONES else "standard"
    faq = KB.by_id.get(faq_id) if faq_id else None
    handoff = None
    if intent == "out_of_scope":
        for reason, pat in OUT_OF_SCOPE_RULES:
            if re.search(pat, masked.lower()):
                handoff = HANDOFF_TEXT[reason]
                break
    if faq and intent != "out_of_scope" and llm.enabled():
        text = llm_reply(masked, faq, tone, escalation)
        if text:
            gate = check_reply(text, faq, masked)
            if gate["status"] != "block":
                return text, "llm"
            print(f"[grounding] AI draft rejected: {[i['detail'] for i in gate['issues']]}")
            return template_reply(intent, faq, tone, escalation, handoff), "template:grounding"
    return template_reply(intent, faq, tone, escalation, handoff), "template"


def analyze(message: str, tone: str | None = None) -> dict:
    t0 = time.perf_counter()
    message = (message or "").strip()
    masked, masked_kinds = mask_pii(message)
    details = extract_details(masked)
    escalation = check_escalation(masked)
    mood = distress_meter(message)
    cls = classify(masked)
    intent = cls["intent"]

    # Safety net: escalation rules force the matching urgent intent if the classifier missed it
    if escalation["level"] == "critical" and intent not in ("card_loss", "suspected_fraud"):
        top = next(r for r in escalation["reasons"] if r["level"] == "critical")
        intent = top.get("intent") or "suspected_fraud"
        cls["rationale"] += f" Overridden to '{INTENTS[intent]}' by escalation rule '{top['rule']}'."
        cls["confidence"] = max(cls["confidence"], 0.9)
    if intent in ("card_loss", "suspected_fraud") and not escalation["escalate"]:
        team = "Card blocking desk" if intent == "card_loss" else "Fraud response team"
        escalation = {"escalate": True, "level": "critical",
                      "reasons": [{"rule": f"Intent is {INTENTS[intent]}", "team": team, "level": "critical", "matched": "intent"}]}

    sources = [] if intent == "out_of_scope" else KB.search(masked, intent=None if intent == "unclear" else intent)
    # A fired escalation rule can name the approved article for that scenario (data/escalation_rules.json)
    hint = next((r["faq"] for r in escalation["reasons"] if r.get("faq") and r.get("intent") == intent), None)
    if hint and intent != "out_of_scope":
        if sources and sources[0]["id"] != hint:
            row = next((x for x in sources if x["id"] == hint), None)
            if row is None:
                f = KB.by_id[hint]
                row = {"id": hint, "title": f["title"], "intent": f["intent"], "score": sources[-1]["score"], "keyword_hits": []}
                sources = sources[:2]
            else:
                sources.remove(row)
            row = {**row, "score": max(row["score"], sources[0]["score"]), "rule_pinned": True}
            sources.insert(0, row)
        elif sources:
            sources[0]["rule_pinned"] = True
    reliable = intent != "out_of_scope" and (KB.is_reliable(sources) or bool(hint))
    faq = KB.by_id[sources[0]["id"]] if reliable else None
    if faq and intent == "unclear":
        intent = faq["intent"]
        cls["rationale"] = "Classifier was unsure; intent taken from the best FAQ match."

    chosen_tone = tone or mood["suggested_tone"]
    reply, reply_source = draft(masked, intent, faq["id"] if faq else None, chosen_tone, escalation)
    compliance = check_reply(reply, faq, masked)
    secondary = cls.get("secondary")
    if secondary and secondary["intent"] in (intent, "out_of_scope"):
        secondary = None

    next_steps = list(faq["steps"]) if faq else (
        ["Explain the request is outside what this assistant can handle.", "Guide the customer to the secure self-service channel or branch."]
        if intent == "out_of_scope" else ["Ask the customer one clarifying question about what they need.", "Re-run the analysis with the extra detail."])
    clarifying = None
    if intent == "failed_transfer" and "reference_numbers" not in details:
        clarifying = "Could you share the transaction reference number (UTR) and the date of the transfer?"
    elif intent == "suspected_fraud" and "amounts_inr" not in details:
        clarifying = "Could you share the date and amount of each transaction you don't recognise?"
    elif not faq and intent != "out_of_scope":
        clarifying = "Is this about a card, a transfer, a charge, your address or a statement?"

    return {
        "analysis_id": uuid.uuid4().hex[:12],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "message_masked": masked,
        "pii_masked": masked_kinds,
        "intent": intent,
        "intent_label": INTENTS.get(intent, "Unclear"),
        "confidence": cls["confidence"],
        "confidence_band": "high" if cls["confidence"] >= 0.75 else "medium" if cls["confidence"] >= 0.55 else "low",
        "rationale": cls["rationale"],
        "secondary_intent": secondary,
        "method": cls["method"],
        "details": details,
        "escalation": escalation,
        "sentiment": mood,
        "sources": sources,
        "faq_match": reliable,
        "faq": faq,
        "no_match_reason": None if reliable or intent == "out_of_scope" else "No approved FAQ matched strongly enough. Do not improvise an answer.",
        "tone": chosen_tone,
        "draft": reply,
        "draft_source": reply_source,
        "compliance": compliance,
        "next_steps": next_steps,
        "required_documents": faq["required_documents"] if faq else [],
        "clarifying_question": clarifying,
        "engine": llm.provider_name(),
        "latency_ms": int((time.perf_counter() - t0) * 1000),
    }


def summarize(record: dict) -> str:
    details = "; ".join(f"{k.replace('_', ' ')}: {', '.join(v)}" for k, v in record.get("details", {}).items()) or "none given"
    faq = f"{record['faq']['id']} ({record['faq']['title']})" if record.get("faq") else "no FAQ match"
    esc = record["escalation"]
    esc_text = (f"escalated to {esc['reasons'][0]['team']} ({esc['reasons'][0]['rule']})" if esc["escalate"] else "no escalation")
    if llm.enabled():
        text = llm.complete(llm.load_prompt("summarize_interaction").format(
            message=record["message_masked"], intent=record["intent_label"], details=details, faq=faq,
            escalation=esc_text, final_reply=record.get("final_reply", record["draft"])), max_tokens=500)
        if text:
            return text
    edited = " The agent edited the drafted reply before use." if record.get("agent_edited") else ""
    return (f"Customer contacted about: {record['intent_label'].lower()}. Details provided: {details}. "
            f"Guidance used: {faq}. Outcome: {esc_text}.{edited}")

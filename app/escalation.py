"""Transparent escalation rules (use-case requirement) and a simple distress meter (value-add).

Rules live in data/escalation_rules.json ("configured escalation scenarios") and are
deliberately deterministic: a safety decision like "hand this to a human now"
should never depend on an LLM's mood. Every rule that fires is shown to the agent.
"""
import json
import re

from .config import DATA_DIR

RULES_FILE = DATA_DIR / "escalation_rules.json"


def load_rules() -> list[dict]:
    """Escalation scenarios are configuration, not code: see data/escalation_rules.json."""
    rules = json.loads(RULES_FILE.read_text(encoding="utf-8"))["rules"]
    for r in rules:
        r["_compiled"] = [re.compile(p, re.I) for p in r["patterns"]]
    return rules


ESCALATION_RULES = load_rules()

DISTRESS_TERMS = [
    "scared", "worried", "panic", "urgent", "immediately", "help!", "please help", "angry", "frustrated",
    "fed up", "worst", "ridiculous", "no refund yet", "still not", "again", "disappointed", "!!",
]


def check_escalation(text: str) -> dict:
    low = text.lower()
    fired = []
    for rule in ESCALATION_RULES:
        for pat in rule["_compiled"]:
            m = pat.search(low)
            if m:
                fired.append({"rule": rule["rule"], "team": rule["team"], "level": rule["level"], "matched": m.group(0),
                              "intent": rule.get("intent"), "faq": rule.get("faq")})
                break
    level = "none"
    if any(f["level"] == "critical" for f in fired):
        level = "critical"
    elif fired:
        level = "high"
    return {"escalate": bool(fired), "level": level, "reasons": fired}


def distress_meter(text: str) -> dict:
    """Very small lexicon-based distress score so the agent picks a suitable tone."""
    low = text.lower()
    hits = [t for t in DISTRESS_TERMS if t in low]
    exclaims = text.count("!")
    score = min(1.0, 0.25 * len(hits) + 0.1 * exclaims)
    label = "calm" if score < 0.25 else "concerned" if score < 0.6 else "distressed"
    suggested = {"calm": "standard", "concerned": "empathetic", "distressed": "empathetic"}[label]
    return {"score": round(score, 2), "label": label, "signals": hits, "suggested_tone": suggested}

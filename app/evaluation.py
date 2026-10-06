"""Runs every labelled message through the pipeline and reports accuracy (criterion: accuracy of verification)."""
import json
from collections import Counter

from .config import DATA_DIR
from .pipeline import analyze


SETS = {
    "tuned": ("messages.json", "30 use-case messages + 5 extra (loan, out-of-scope). Keywords were tuned on these."),
    "unseen": ("messages_unseen.json", "20 new wordings written after the rules were built, to measure generalisation."),
}


def _pct(k, total):
    return round(100 * k / total, 1) if total else 0.0


def _score(cases: list[dict], set_name: str) -> tuple[list[dict], dict, Counter]:
    rows, confusion = [], Counter()
    for c in cases:
        r = analyze(c["text"], tone="standard")
        got_faq = r["faq"]["id"] if r["faq"] else None
        top3 = [s["id"] for s in r["sources"]]
        row = {
            "set": set_name,
            "id": c["id"],
            "text": c["text"],
            "expected_intent": c["expected_intent"],
            "predicted_intent": r["intent"],
            "intent_ok": r["intent"] == c["expected_intent"],
            "expected_faq": c["expected_faq"],
            "predicted_faq": got_faq,
            "faq_ok": got_faq == c["expected_faq"],
            "faq_in_top3": c["expected_faq"] is None or c["expected_faq"] in top3,
            "expected_escalation": c["expected_escalation"],
            "predicted_escalation": r["escalation"]["escalate"],
            "escalation_ok": r["escalation"]["escalate"] == c["expected_escalation"],
            "compliance": r["compliance"]["status"],
            "confidence": r["confidence"],
            "latency_ms": r["latency_ms"],
        }
        rows.append(row)
        if not row["intent_ok"]:
            confusion[f"{c['expected_intent']} -> {r['intent']}"] += 1

    n = len(rows)
    esc_pos = [r for r in rows if r["expected_escalation"]]
    esc_pred = [r for r in rows if r["predicted_escalation"]]
    metrics = {
        "cases": n,
        "intent_accuracy": _pct(sum(r["intent_ok"] for r in rows), n),
        "faq_top1_accuracy": _pct(sum(r["faq_ok"] for r in rows), n),
        "faq_top3_recall": _pct(sum(r["faq_in_top3"] for r in rows), n),
        "escalation_recall": _pct(sum(r["predicted_escalation"] for r in esc_pos), len(esc_pos)),
        "escalation_precision": _pct(sum(r["expected_escalation"] for r in esc_pred), len(esc_pred)),
        "drafts_passing_compliance": _pct(sum(r["compliance"] == "pass" for r in rows), n),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / n, 1) if n else 0.0,
    }
    return rows, metrics, confusion


def run_evaluation() -> dict:
    """Scores both labelled sets. `metrics` is the development set (kept for backwards compatibility);
    `sets` holds both, so the held-out score is always shown next to the tuned one."""
    all_rows, sets, confusion = [], {}, Counter()
    for name, (fname, desc) in SETS.items():
        path = DATA_DIR / fname
        if not path.exists():
            continue
        rows, metrics, conf = _score(json.loads(path.read_text(encoding="utf-8")), name)
        all_rows += rows
        sets[name] = {"description": desc, **metrics}
        confusion.update({f"[{name}] {k}": v for k, v in conf.items()})
    return {"metrics": sets["tuned"], "sets": sets, "misclassified": dict(confusion), "rows": all_rows}


BASELINE_UNSEEN = {  # first run of the held-out set, before the v1.1 rule upgrades (kept for transparency)
    "intent_accuracy": 65.0, "faq_top1_accuracy": 55.0, "escalation_recall": 28.6,
}


def write_report(result: dict, path) -> None:
    sets = result["sets"]
    names = list(sets)
    label = {"tuned": "Development set", "unseen": "Held-out set"}
    rows_def = [
        ("Labelled cases", "cases", ""),
        ("Intent accuracy", "intent_accuracy", "%"),
        ("FAQ top-1 accuracy", "faq_top1_accuracy", "%"),
        ("FAQ top-3 recall", "faq_top3_recall", "%"),
        ("Escalation recall (urgent cases caught)", "escalation_recall", "%"),
        ("Escalation precision", "escalation_precision", "%"),
        ("Drafts passing the compliance check", "drafts_passing_compliance", "%"),
        ("Average latency", "avg_latency_ms", " ms"),
    ]
    lines = [
        "# Verification report",
        "",
        "Offline mode (rules + templates). Regenerate with `python -m eval.evaluate`.",
        "",
    ]
    for n in names:
        lines.append(f"- **{label.get(n, n)}**: {sets[n]['description']}")
    lines += ["", "| Metric | " + " | ".join(label.get(n, n) for n in names) + " |",
              "|---|" + "---|" * len(names)]
    for title, key, unit in rows_def:
        lines.append(f"| {title} | " + " | ".join(f"{sets[n][key]}{unit}" for n in names) + " |")

    if "unseen" in sets:
        u = sets["unseen"]
        lines += [
            "",
            "## What the held-out set taught us",
            "",
            "The first run of the held-out set (before v1.1) exposed that the rules were overfitted to the development wording:",
            "",
            "| Held-out metric | First run (v1.0) | Now (v1.1) |",
            "|---|---|---|",
            f"| Intent accuracy | {BASELINE_UNSEEN['intent_accuracy']}% | {u['intent_accuracy']}% |",
            f"| FAQ top-1 accuracy | {BASELINE_UNSEEN['faq_top1_accuracy']}% | {u['faq_top1_accuracy']}% |",
            f"| Urgent cases caught | {BASELINE_UNSEEN['escalation_recall']}% | {u['escalation_recall']}% |",
            "",
            "Missed urgent cases were phrased in ways the rules had not seen (\"purse got snatched\", \"left my card at the restaurant\", "
            "\"debit alert I don't recognise\", \"caller asked me to install an app\"). We broadened the escalation lexicon with general "
            "synonyms (not the exact test sentences), moved the rules into `data/escalation_rules.json`, and let each rule name its "
            "approved FAQ. Because the held-out set has now been looked at once, it is no longer fully blind: add fresh messages to "
            "`data/messages_unseen.json` for the next honest score.",
        ]

    if result["misclassified"]:
        lines += ["", "## Intent errors", ""] + [f"- {k}: {v}" for k, v in result["misclassified"].items()]

    lines += ["", "## Case by case", "",
              "| Set | ID | Expected intent | Predicted | FAQ expected | FAQ predicted | Escalation | Result |",
              "|---|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        ok = r["intent_ok"] and r["faq_ok"] and r["escalation_ok"]
        lines.append(f"| {r['set']} | {r['id']} | {r['expected_intent']} | {r['predicted_intent']} | {r['expected_faq'] or '-'} | "
                     f"{r['predicted_faq'] or '-'} | {'yes' if r['predicted_escalation'] else 'no'} | {'pass' if ok else 'CHECK'} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

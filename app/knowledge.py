"""FAQ loading, BM25 retrieval and rule-based intent classification.

No external ML libraries: pure-Python BM25 keeps the prototype fast, explainable and offline.
"""
import json
import math
import re
from collections import Counter

from .config import DATA_DIR, MIN_RETRIEVAL_SCORE

INTENTS = {
    "card_delivery": "Card delivery",
    "fee_explanation": "Fee explanation",
    "address_update": "Address update",
    "failed_transfer": "Failed or pending transfer",
    "statement_request": "Statement request",
    "card_loss": "Card loss",
    "suspected_fraud": "Suspected fraud",
    "loan_documents": "Loan documents",
    "out_of_scope": "Out of scope",
}

# Requests the assistant must NOT handle (authentication, balances, transactions, advice)
OUT_OF_SCOPE_RULES = [
    ("Balance enquiry needs authenticated access", r"\b(?:account|current|available|my) balance\b(?!.*\b(?:went|gone|reduced|deducted|charge|penalty|fee))|\bhow much (?:money|balance) (?:do i have|is (?:there )?in|is left|is available)\b|\b(?:check|tell me|show) my balance\b"),
    ("Financial or investment advice is not provided", r"\binvest\w*\b|\bmutual funds?\b|\bshould i (?:buy|put|keep|sell)\b|\bstocks?\b|\bwhich (?:fund|scheme)\b|\bgood time to (?:buy|sell|invest)\b|\bgold bonds?\b|\bcrypto\w*\b|\b(?:share|stock) market\b|\bbest (?:fd|fixed deposit|returns?)\b"),
    ("Assistant cannot perform transactions", r"\b(?:transfer|send|pay)\s+(?:rs\.?\s*|₹\s*|inr\s*)?\d[\d,]*\b(?!.*\b(?:failed|debited|deducted|pending|not)\b)"),
    ("Login, password or PIN reset needs authentication", r"\breset (?:my )?(?:password|pin|mpin)\b|\bunlock (?:my )?(?:net ?banking|account)\b"),
]

STOPWORDS = set(
    "a an the i my me we our you your is are was were be been to of in on for at by it this that and or but "
    "with from as can could would should will do does did how what why when where which who please hi hello "
    "there have has had not no so if any some just still now get got its im".split()
)


def _stem(tok: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(tok) > 4 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))
    return [_stem(t) for t in toks if t not in STOPWORDS and len(t) > 1]


class KnowledgeBase:
    def __init__(self, faqs: list[dict]):
        self.faqs = faqs
        self.by_id = {f["id"]: f for f in faqs}
        self.docs = []
        for f in faqs:
            text = " ".join([f["title"], f["title"], f["answer"], " ".join(f["keywords"])])
            self.docs.append(tokenize(text))
        self.avgdl = sum(len(d) for d in self.docs) / len(self.docs)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    @classmethod
    def load(cls) -> "KnowledgeBase":
        with open(DATA_DIR / "faqs.json", encoding="utf-8") as fh:
            return cls(json.load(fh))

    # ---------- retrieval ----------
    def _bm25(self, q_toks: list[str], i: int, k1=1.4, b=0.75) -> float:
        tf, dl = self.tf[i], len(self.docs[i])
        s = 0.0
        for t in q_toks:
            if t in tf:
                s += self.idf[t] * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / self.avgdl))
        return s

    def keyword_hits(self, text: str, faq: dict) -> list[str]:
        low = text.lower().replace("’", "'")
        return [k for k in faq["keywords"] if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", low)]

    def search(self, text: str, intent: str | None = None, top_k: int = 3) -> list[dict]:
        q = tokenize(text)
        rows = []
        for i, f in enumerate(self.faqs):
            bm = self._bm25(q, i)
            hits = self.keyword_hits(text, f)
            score = bm + 3.5 * len(hits)
            if intent and f["intent"] == intent:
                score *= 1.35
            rows.append({"faq": f, "bm25": bm, "keyword_hits": hits, "raw": score})
        rows.sort(key=lambda r: r["raw"], reverse=True)
        top = rows[0]["raw"] or 1.0
        out = []
        for r in rows[:top_k]:
            # absolute strength (saturating) times relative strength vs best
            strength = 1 - math.exp(-r["raw"] / 8.0)
            out.append({
                "id": r["faq"]["id"],
                "title": r["faq"]["title"],
                "intent": r["faq"]["intent"],
                "score": round(strength * (r["raw"] / top), 3),
                "keyword_hits": r["keyword_hits"],
            })
        return out

    # ---------- intent ----------
    def classify(self, text: str) -> dict:
        """Score each intent from FAQ keyword hits + BM25, with explicit out-of-scope rules."""
        for reason, pat in OUT_OF_SCOPE_RULES:
            m = re.search(pat, text.lower())
            if m:
                return {
                    "intent": "out_of_scope",
                    "confidence": 0.9,
                    "rationale": f"Out-of-scope rule: {reason} (matched '{m.group(0).strip()}').",
                    "scores": {},
                    "method": "rules",
                }
        q = tokenize(text)
        scores: dict[str, float] = {}
        evidence: dict[str, list[str]] = {}
        for i, f in enumerate(self.faqs):
            hits = self.keyword_hits(text, f)
            s = self._bm25(q, i) + 2.5 * len(hits)
            if s > scores.get(f["intent"], 0):
                scores[f["intent"]] = s
                evidence[f["intent"]] = hits
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        if not ranked or ranked[0][1] < 1.5:
            return {"intent": "unclear", "confidence": 0.0, "rationale": "No strong signal for any configured intent.",
                    "scores": {}, "method": "rules"}
        best, best_s = ranked[0]
        second_s = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = (best_s - second_s) / best_s
        confidence = round(min(0.98, 0.45 + 0.5 * margin + 0.02 * min(best_s, 10)), 2)
        hits = evidence.get(best, [])
        rationale = (f"Matched phrases {', '.join(repr(h) for h in hits)}" if hits else "Matched by overall wording (BM25)")
        rationale += f"; ahead of '{INTENTS.get(ranked[1][0], ranked[1][0])}' by {margin:.0%}." if len(ranked) > 1 else "."
        # Multi-issue detection (value-add): a second intent with its own phrase evidence and a close score
        secondary = None
        if len(ranked) > 1:
            sec, sec_s = ranked[1]
            sec_hits = evidence.get(sec, [])
            if sec_hits and sec_s >= 0.5 * best_s and not set(sec_hits) <= set(hits):
                secondary = {"intent": sec, "label": INTENTS.get(sec, sec), "evidence": sec_hits}
        return {
            "intent": best,
            "confidence": confidence,
            "rationale": rationale,
            "scores": {k: round(v, 2) for k, v in ranked[:4]},
            "method": "rules",
            "secondary": secondary,
        }

    def is_reliable(self, results: list[dict]) -> bool:
        return bool(results) and results[0]["score"] >= MIN_RETRIEVAL_SCORE

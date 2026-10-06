"""Reply compliance and grounding check (value-add).

Runs on every draft (AI or template) and again on the agent's edited text before saving.
It answers one question: "is this reply still inside the approved guidance and safe to send?"

Checks (all deterministic, so the agent sees exactly why something was flagged):
  1. Asks the customer for an OTP, PIN, CVV or password.
  2. Promises an outcome or claims an action was already taken (refund done, card blocked...).
  3. Contains unmasked personal data (card, account, phone, email).
  4. Contains a link or web address (customers should only use official channels).
  5. Gives financial or investment advice.
  6. Quotes a figure (days, hours, fee, percentage) that is not in the approved FAQ or the customer's message.

The same check is the grounding gate for AI drafts: an AI draft with any issue is discarded and the
template reply (built word-for-word from the FAQ) is used instead.
"""
import re

from .extract import mask_pii

NEGATION = re.compile(r"\b(?:never|not|don'?t|do not|no one|nobody|without)\b[^.!?\n]{0,40}$", re.I)

SECRET_RE = re.compile(
    r"\b(?:share|send|tell|provide|give|confirm|enter|type|read out)\b[^.!?\n]{0,40}?\b(otp|pin|cvv|password|mpin|card number)\b",
    re.I,
)
PROMISE_RE = re.compile(
    r"\bguarantee\w*\b|\bdefinitely\b|\b100 ?%|\bwill be refunded (?:today|immediately|now)\b"
    r"|\b(?:we|i) have (?:already )?(?:blocked|refunded|reversed|credited|waived|cancelled|updated)\b"
    r"|\bhas been (?:refunded|reversed|credited|waived)\b",
    re.I,
)
LINK_RE = re.compile(r"https?://\S+|\bwww\.\S+|\b[a-z0-9-]+\.(?:com|in|net|org|co)\b(?!\S*@)", re.I)
ADVICE_RE = re.compile(r"\byou should (?:invest|buy|sell)\b|\b(?:i|we) (?:recommend|suggest) (?:investing|buying|selling)\b"
                       r"|\bbest (?:investment|fund|scheme)\b", re.I)
FIGURE_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s*[\d,]+(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s*(?:%|percent|working days?|days?|hours?|hrs|minutes?|months?|years?|rupees)",
    re.I,
)


UNIT_CORE = [("%", "pct"), ("percent", "pct"), ("hour", "hour"), ("hr", "hour"), ("minute", "minute"),
             ("month", "month"), ("year", "year"), ("day", "day"), ("rs", "rs"), ("rupee", "rs"), ("inr", "rs"), ("₹", "rs")]


def _norm_fig(s: str) -> str:
    """'5 working days' -> '5:day', 'Rs 1,250' -> '1250:rs'."""
    low = s.lower().replace(",", "")
    num = re.search(r"\d+(?:\.\d+)?", low)
    unit = next((core for key, core in UNIT_CORE if key in low), "")
    return f"{num.group(0) if num else ''}:{unit}"


def _figures(text: str) -> set[str]:
    return {_norm_fig(m.group(0)) for m in FIGURE_RE.finditer(text or "")}


def check_reply(reply: str, faq: dict | None = None, message: str = "") -> dict:
    issues: list[dict] = []
    text = reply or ""

    for m in SECRET_RE.finditer(text):
        if not NEGATION.search(text[: m.start()]):
            issues.append({"check": "asks_for_secret", "severity": "block",
                           "detail": f"Asks the customer for their {m.group(1).upper()}: \"{m.group(0).strip()}\""})
            break

    m = PROMISE_RE.search(text)
    if m:
        issues.append({"check": "promise_or_claim", "severity": "block",
                       "detail": f"Promises an outcome or claims an action already happened: \"{m.group(0).strip()}\""})

    _, kinds = mask_pii(text)
    if kinds:
        issues.append({"check": "personal_data", "severity": "block",
                       "detail": f"Contains unmasked personal data: {', '.join(kinds)}"})

    approved = ""
    if faq:
        approved = " ".join([faq.get("answer", ""), " ".join(faq.get("steps", [])), " ".join(faq.get("required_documents", []))])
    m = LINK_RE.search(text)
    if m and m.group(0).lower() not in approved.lower():
        issues.append({"check": "link", "severity": "warn",
                       "detail": f"Contains a link or web address not in the approved FAQ: \"{m.group(0)}\""})

    m = ADVICE_RE.search(text)
    if m:
        issues.append({"check": "financial_advice", "severity": "block",
                       "detail": f"Reads as financial advice: \"{m.group(0)}\""})

    if faq:
        allowed = _figures(approved) | _figures(message)
        unverified = [fm.group(0).strip() for fm in FIGURE_RE.finditer(text) if _norm_fig(fm.group(0)) not in allowed]
        if unverified:
            issues.append({"check": "unverified_figure", "severity": "block",
                           "detail": "Quotes figures not found in the approved FAQ: " + ", ".join(sorted(set(unverified)))})

    status = "block" if any(i["severity"] == "block" for i in issues) else "warn" if issues else "pass"
    return {"status": status, "issues": issues}

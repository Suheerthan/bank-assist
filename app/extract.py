"""PII masking (value-add) and extraction of request details from a customer message.

Everything here is deterministic regex so the agent can see exactly what was found.
"""
import re

CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+91[ -]?)?([6-9]\d{1})\d{6}(\d{2})(?!\d)")
ACCOUNT_RE = re.compile(r"\b(a/c|acc(?:ount)?\.?\s*(?:no\.?|number)?)\s*[:#]?\s*(\d{5,14})(\d{4})\b", re.I)


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Mask card numbers, account numbers, phone numbers and emails. Returns (masked_text, kinds_masked)."""
    found: list[str] = []

    def _card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        # 12-digit plain numbers are usually UTR references, keep them
        if len(digits) < 13 or (len(digits) == 12 and " " not in m.group(0)):
            return m.group(0)
        found.append("card number")
        return "XXXX XXXX XXXX " + digits[-4:]

    text = CARD_RE.sub(_card, text)

    def _acct(m: re.Match) -> str:
        found.append("account number")
        return f"{m.group(1)} XXXXXX{m.group(3)}"

    text = ACCOUNT_RE.sub(_acct, text)

    def _phone(m: re.Match) -> str:
        found.append("phone number")
        return f"{m.group(1)}XXXXXX{m.group(2)}"

    text = PHONE_RE.sub(_phone, text)

    def _email(m: re.Match) -> str:
        found.append("email")
        return f"{m.group(1)}***{m.group(2)}"

    text = EMAIL_RE.sub(_email, text)
    return text, sorted(set(found))


AMOUNT_RE = re.compile(
    r"(?:(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?))|(?:([\d,]+(?:\.\d{1,2})?)\s*(?:rupees|rs\b|inr))"
    r"|(?:(?:by|of|amount|debited|deducted|lost)\s+([\d,]{3,}))",
    re.I,
)
REF_RE = re.compile(r"\b(?:utr|rrn|ref(?:erence)?(?:\s*no\.?)?|txn\s*id)\s*[:#]?\s*([A-Z0-9]{8,22})\b", re.I)
PLAIN_REF_RE = re.compile(r"(?<![\d ])(\d{12})(?![\d])")
CHANNELS = ["UPI", "NEFT", "IMPS", "RTGS", "ATM", "POS", "net banking", "mobile app", "online shopping"]
TIME_WORDS = [
    "today", "yesterday", "this morning", "last night", "overnight", "last week", "last month",
    "since morning", "since yesterday", "two years ago",
]
DAYS_AGO_RE = re.compile(r"\b(\d+)\s+(?:working\s+)?days?\s+(?:ago|back)\b|\b(\d+)\s+days\b", re.I)
CARD_TYPE_RE = re.compile(r"\b(debit|credit|replacement|new)\s+card\b", re.I)
LAST4_RE = re.compile(r"XXXX XXXX XXXX (\d{4})")


def extract_details(masked_text: str) -> dict:
    """Pull out the request details an agent needs: amounts, references, channel, timing, card."""
    low = masked_text.lower()
    amounts = []
    for m in AMOUNT_RE.finditer(masked_text):
        val = next(g for g in m.groups() if g)
        val = val.replace(",", "")
        if val and val not in amounts:
            amounts.append(val)
    refs = [m.group(1) for m in REF_RE.finditer(masked_text)]
    refs += [r for r in PLAIN_REF_RE.findall(masked_text) if r not in refs]
    channels = [c for c in CHANNELS if re.search(r"\b" + re.escape(c.lower()) + r"\b", low)]
    when = [w for w in TIME_WORDS if w in low]
    for m in DAYS_AGO_RE.finditer(masked_text):
        when.append(m.group(0))
    card_types = sorted({m.group(1).lower() for m in CARD_TYPE_RE.finditer(masked_text)})
    last4 = LAST4_RE.findall(masked_text)

    details = {
        "amounts_inr": amounts,
        "reference_numbers": refs,
        "channel": channels,
        "timing": when,
        "card": [f"{t} card" for t in card_types] + [f"card ending {l}" for l in last4],
    }
    return {k: v for k, v in details.items() if v}

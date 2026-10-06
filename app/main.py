"""FastAPI entry point. Run with:  uvicorn app.main:app --reload"""
import csv
import io
import json
from collections import Counter
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, llm
from .compliance import check_reply
from .evaluation import run_evaluation
from .extract import mask_pii
from .knowledge import INTENTS
from .pipeline import KB, TONES, analyze, draft, summarize
from .storage import Store

app = FastAPI(title=f"{config.BANK_NAME} Agent Assist", version="1.1")
store = Store()
STATIC = config.BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AnalyzeIn(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    tone: str | None = None


class DraftIn(BaseModel):
    message: str
    intent: str
    faq_id: str | None = None
    tone: str = "standard"
    escalation: dict


class SaveIn(BaseModel):
    analysis: dict
    final_reply: str = Field(min_length=1)
    agent_notes: str = ""
    agent_name: str = "Agent"


class CheckIn(BaseModel):
    reply: str
    faq_id: str | None = None
    message: str = ""


class FeedbackIn(BaseModel):
    analysis_id: str
    faq_id: str | None = None
    helpful: bool
    comment: str = ""


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": llm.provider_name(), "storage": store.backend, "faqs": len(KB.faqs), "bank": config.BANK_NAME}


@app.get("/api/samples")
def samples():
    rows = json.loads((config.DATA_DIR / "messages.json").read_text(encoding="utf-8"))
    unseen = config.DATA_DIR / "messages_unseen.json"
    if unseen.exists():
        rows += json.loads(unseen.read_text(encoding="utf-8"))
    return rows


@app.get("/api/faqs")
def faqs():
    return KB.faqs


@app.post("/api/analyze")
def api_analyze(body: AnalyzeIn):
    if body.tone and body.tone not in TONES:
        raise HTTPException(400, f"tone must be one of {list(TONES)}")
    return analyze(body.message, body.tone)


@app.post("/api/draft")
def api_draft(body: DraftIn):
    """Re-draft the reply in another tone. The FAQ guidance stays exactly the same."""
    masked, _ = mask_pii(body.message)
    text, source = draft(masked, body.intent, body.faq_id, body.tone, body.escalation)
    return {"draft": text, "draft_source": source, "tone": body.tone}


@app.post("/api/check")
def api_check(body: CheckIn):
    """Compliance and grounding check on the agent's edited reply (runs live as they type)."""
    masked, _ = mask_pii(body.message)
    return check_reply(body.reply, KB.by_id.get(body.faq_id) if body.faq_id else None, masked)


@app.post("/api/interactions")
def save_interaction(body: SaveIn):
    a = body.analysis
    final_masked, _ = mask_pii(body.final_reply)
    record = {
        "analysis_id": a.get("analysis_id"),
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent_name": body.agent_name,
        "message_masked": a.get("message_masked"),
        "intent": a.get("intent"),
        "intent_label": a.get("intent_label"),
        "confidence": a.get("confidence"),
        "details": a.get("details", {}),
        "escalation": a.get("escalation", {"escalate": False, "reasons": []}),
        "faq": a.get("faq"),
        "draft": a.get("draft", ""),
        "final_reply": final_masked,
        "agent_edited": final_masked.strip() != (a.get("draft") or "").strip(),
        "agent_notes": body.agent_notes,
        "tone": a.get("tone"),
        "sent_automatically": False,
        "secondary_intent": (a.get("secondary_intent") or {}).get("label"),
    }
    # Check what the agent actually approved (before masking, so leaked personal data is caught)
    check = check_reply(body.final_reply, a.get("faq"), a.get("message_masked") or "")
    record["compliance_status"] = check["status"]
    record["compliance_issues"] = [i["detail"] for i in check["issues"]]
    record["summary"] = summarize(record)
    record["faq_id"] = (record["faq"] or {}).get("id")
    record.pop("faq")
    store.insert("interactions", record)
    return record


@app.get("/api/interactions")
def list_interactions():
    return store.all("interactions")


@app.get("/api/interactions.csv")
def export_interactions():
    """Download all saved interactions as CSV for record keeping."""
    cols = ["saved_at", "agent_name", "intent_label", "secondary_intent", "confidence", "faq_id", "escalated",
            "escalation_team", "tone", "agent_edited", "compliance_status", "summary", "final_reply", "agent_notes"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in store.all("interactions", limit=10000):
        esc = r.get("escalation") or {}
        w.writerow({**r, "escalated": bool(esc.get("escalate")),
                    "escalation_team": (esc.get("reasons") or [{}])[0].get("team", "") if esc.get("escalate") else ""})
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=interactions.csv"})


@app.post("/api/feedback")
def feedback(body: FeedbackIn):
    doc = body.model_dump() | {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    store.insert("feedback", doc)
    return {"ok": True}


@app.get("/api/stats")
def stats():
    rows = store.all("interactions", limit=1000)
    fb = store.all("feedback", limit=1000)
    by_intent = Counter(r.get("intent_label") or r.get("intent") for r in rows)
    return {
        "interactions": len(rows),
        "escalations": sum(1 for r in rows if r.get("escalation", {}).get("escalate")),
        "edited_by_agent": sum(1 for r in rows if r.get("agent_edited")),
        "compliance_flagged": sum(1 for r in rows if r.get("compliance_status") not in (None, "pass")),
        "by_intent": dict(by_intent.most_common()),
        "feedback_helpful": sum(1 for f in fb if f.get("helpful")),
        "feedback_not_helpful": sum(1 for f in fb if not f.get("helpful")),
        "intents": INTENTS,
    }


@app.post("/api/evaluate")
def evaluate():
    return run_evaluation()

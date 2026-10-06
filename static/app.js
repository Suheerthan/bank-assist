const $ = (s) => document.querySelector(s);
let current = null;      // last analysis result
let currentTone = "standard";
let toneTouched = false;

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ? JSON.stringify(err.detail) : `Request failed (${res.status})`);
  }
  return res.json();
}

function esc(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- tabs ---------- */
document.querySelectorAll(".tabs button").forEach((btn) => btn.addEventListener("click", () => {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b === btn));
  ["assist", "history", "verify"].forEach((t) => { $(`#panel-${t}`).hidden = t !== btn.dataset.tab; });
  if (btn.dataset.tab === "history") loadHistory();
}));

/* ---------- init ---------- */
async function init() {
  try {
    const h = await api("/api/health");
    $("#status").textContent = `${h.engine} | storage: ${h.storage === "mongodb" ? "MongoDB" : "local file"} | ${h.faqs} FAQs`;
  } catch { $("#status").textContent = "Server not reachable"; }
  const samples = await api("/api/samples");
  const sel = $("#sample");
  samples.forEach((s) => {
    const o = document.createElement("option");
    o.value = s.text;
    o.textContent = `${s.id}: ${s.text.slice(0, 60)}${s.text.length > 60 ? "…" : ""}`;
    sel.appendChild(o);
  });
}
$("#sample").addEventListener("change", (e) => { if (e.target.value) $("#message").value = e.target.value; });

/* ---------- tone ---------- */
function setTone(t) {
  currentTone = t;
  document.querySelectorAll(".tone button").forEach((b) => b.setAttribute("aria-checked", b.dataset.tone === t));
}
document.querySelectorAll(".tone button").forEach((b) => b.addEventListener("click", async () => {
  toneTouched = true;
  setTone(b.dataset.tone);
  if (!current) return;
  const r = await api("/api/draft", {
    message: $("#message").value, intent: current.intent, faq_id: current.faq ? current.faq.id : null,
    tone: currentTone, escalation: current.escalation,
  });
  current.draft = r.draft; current.tone = r.tone;
  $("#draft").value = r.draft;
  $("#draft-meta").textContent = draftMeta(r.draft_source, r.tone);
  runCheck();
}));

/* ---------- live compliance check on the agent's text ---------- */
let checkTimer = null, lastCheck = null, confirmPending = false;
function renderCompliance(c) {
  lastCheck = c;
  const box = $("#compliance");
  box.className = `compliance ${c.status}`;
  if (c.status === "pass") {
    box.innerHTML = "<strong>Compliance check passed.</strong> No secrets requested, no promises, no personal data, no figures outside the approved FAQ.";
  } else {
    const head = c.status === "block" ? "Fix before sending:" : "Please review:";
    box.innerHTML = `<strong>${head}</strong><ul>${c.issues.map((i) => `<li>${esc(i.detail)}</li>`).join("")}</ul>`;
  }
  confirmPending = false;
  $("#save").textContent = saveLabel();
}
async function runCheck() {
  if (!current) return;
  const c = await api("/api/check", { reply: $("#draft").value, faq_id: current.faq ? current.faq.id : null, message: $("#message").value });
  renderCompliance(c);
}
$("#draft").addEventListener("input", () => { clearTimeout(checkTimer); checkTimer = setTimeout(runCheck, 350); });
function saveLabel() {
  if (confirmPending) return "Save anyway (flags recorded)";
  return current && current.escalation.escalate ? "Approve, save and hand off" : "Approve and save";
}

function draftMeta(source, tone) {
  const how = source === "llm" ? "Written by the AI model from the approved FAQ and passed the grounding check"
    : source === "template:grounding" ? "AI draft failed the grounding check, so the approved template was used"
    : "Built from approved templates";
  return `${how}. Tone: ${tone}. Review before use; nothing is sent automatically.`;
}

/* ---------- analyse ---------- */
$("#analyze").addEventListener("click", runAnalysis);
$("#message").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) runAnalysis(); });

async function runAnalysis() {
  const text = $("#message").value.trim();
  if (text.length < 3) { $("#message").focus(); return; }
  const btn = $("#analyze");
  btn.disabled = true; btn.textContent = "Analysing…";
  try {
    current = await api("/api/analyze", { message: text, tone: toneTouched ? currentTone : null });
    render(current);
  } catch (e) {
    alert(`Analysis failed: ${e.message}`);
  } finally {
    btn.disabled = false; btn.textContent = "Analyse message";
  }
}

function render(a) {
  setTone(a.tone);
  // escalation band
  const alarm = $("#alarm");
  document.body.classList.toggle("alarmed", a.escalation.escalate);
  if (a.escalation.escalate) {
    const r = a.escalation.reasons[0];
    $("#alarm-title").textContent = `Hand off to the ${r.team} now`;
    $("#alarm-detail").textContent = `${r.rule}. Triggered by "${r.matched}".`;
    alarm.hidden = false; alarm.classList.remove("flash"); void alarm.offsetWidth; alarm.classList.add("flash");
  } else {
    alarm.hidden = true;
  }
  confirmPending = false;
  $("#save").textContent = saveLabel();

  // message column
  $("#message-out").hidden = false;
  $("#masked").textContent = a.message_masked;
  $("#pii").textContent = a.pii_masked.length ? `Masked: ${a.pii_masked.join(", ")}` : "No personal data detected.";
  const d = a.details, dl = $("#details");
  const labels = { amounts_inr: "Amount (INR)", reference_numbers: "Reference", channel: "Channel", timing: "When", card: "Card" };
  dl.innerHTML = Object.keys(d).length
    ? Object.entries(d).map(([k, v]) => `<dt>${labels[k] || k}</dt><dd>${esc(v.join(", "))}</dd>`).join("")
    : "<dd>No specific details found.</dd>";
  $("#mood").textContent = `${a.sentiment.label[0].toUpperCase() + a.sentiment.label.slice(1)}${a.sentiment.signals.length ? ` (signals: ${a.sentiment.signals.join(", ")})` : ""}. Suggested tone: ${a.sentiment.suggested_tone}.`;

  // draft column
  $("#empty-draft").hidden = true; $("#draft-wrap").hidden = false; $("#saved").hidden = true;
  $("#draft").value = a.draft;
  $("#draft-meta").textContent = draftMeta(a.draft_source, a.tone);
  $("#notes").value = "";
  renderCompliance(a.compliance);
  const nm = $("#nomatch");
  if (a.intent === "out_of_scope") { nm.hidden = false; nm.textContent = "Outside this assistant's scope. Use the safe hand-off reply below."; }
  else if (a.no_match_reason) { nm.hidden = false; nm.textContent = a.no_match_reason; }
  else nm.hidden = true;
  $("#clarify").hidden = !a.clarifying_question;
  $("#clarify").textContent = a.clarifying_question ? `Ask the customer: ${a.clarifying_question}` : "";

  // analysis column
  $("#analysis-empty").hidden = true; $("#analysis").hidden = false;
  $("#intent-name").textContent = a.intent_label;
  const fill = $("#meter-fill");
  fill.className = a.confidence_band; fill.style.width = `${Math.round(a.confidence * 100)}%`;
  $("#intent-conf").textContent = `${Math.round(a.confidence * 100)}% confidence (${a.confidence_band})`;
  $("#rationale").textContent = a.rationale;
  const also = $("#also");
  if (a.secondary_intent) {
    also.hidden = false;
    also.textContent = `The customer also mentions: ${a.secondary_intent.label} (phrases: ${a.secondary_intent.evidence.join(", ")}). Handle it after this request, or analyse it separately.`;
  } else also.hidden = true;

  const usedId = a.faq ? a.faq.id : null;
  $("#sources").innerHTML = a.sources.length ? a.sources.map((s) => `
    <li class="${s.id === usedId ? "used" : ""}">
      <span class="src-title">${esc(s.id)}: ${esc(s.title)}</span>
      <span class="src-meta">
        <span>Match ${Math.round(s.score * 100)}%${s.id === usedId ? ", used for the draft" : ""}${s.rule_pinned ? ' <span class="pin">chosen by escalation rule</span>' : ""}</span>
        <span class="fb" data-faq="${esc(s.id)}">
          <button data-h="1" aria-label="Helpful source">Helpful</button>
          <button data-h="0" aria-label="Not helpful source">Not helpful</button>
        </span>
      </span>
    </li>`).join("") : "<li>No FAQ is used for out-of-scope requests.</li>";
  document.querySelectorAll(".fb button").forEach((b) => b.addEventListener("click", async () => {
    const wrap = b.parentElement;
    wrap.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    await api("/api/feedback", { analysis_id: a.analysis_id, faq_id: wrap.dataset.faq, helpful: b.dataset.h === "1" });
  }));

  $("#steps").innerHTML = a.next_steps.map((s, i) => `<li><input type="checkbox" id="st${i}"><label for="st${i}">${esc(s)}</label></li>`).join("");
  $("#docs").innerHTML = a.required_documents.length ? a.required_documents.map((x) => `<li>${esc(x)}</li>`).join("") : "<li>None for this request.</li>";
}

/* ---------- copy & save ---------- */
$("#copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("#draft").value); $("#copy").textContent = "Copied"; }
  catch { $("#draft").select(); document.execCommand("copy"); $("#copy").textContent = "Copied"; }
  setTimeout(() => { $("#copy").textContent = "Copy reply"; }, 1500);
});

$("#save").addEventListener("click", async () => {
  if (!current) return;
  if (lastCheck && lastCheck.status === "block" && !confirmPending) {
    confirmPending = true; $("#save").textContent = saveLabel(); return;
  }
  confirmPending = false;
  const btn = $("#save"); btn.disabled = true;
  try {
    const rec = await api("/api/interactions", { analysis: current, final_reply: $("#draft").value, agent_notes: $("#notes").value });
    $("#summary").textContent = rec.summary + (rec.agent_edited ? " (Reply edited by agent.)" : "")
      + (rec.compliance_status !== "pass" ? ` Compliance flags recorded: ${rec.compliance_issues.length}.` : "");
    $("#saved").hidden = false;
  } catch (e) { alert(`Save failed: ${e.message}`); }
  finally { btn.disabled = false; btn.textContent = saveLabel(); }
});

/* ---------- history ---------- */
async function loadHistory() {
  const [rows, st] = await Promise.all([api("/api/interactions"), api("/api/stats")]);
  $("#stats").innerHTML = `
    <div class="stat"><b>${st.interactions}</b><span>Interactions saved</span></div>
    <div class="stat warn"><b>${st.escalations}</b><span>Escalated to a human</span></div>
    <div class="stat"><b>${st.edited_by_agent}</b><span>Replies edited by agent</span></div>
    <div class="stat${st.compliance_flagged ? " warn" : ""}"><b>${st.compliance_flagged}</b><span>Saved with compliance flags</span></div>
    <div class="stat"><b>${st.feedback_helpful} / ${st.feedback_not_helpful}</b><span>Source feedback (helpful / not)</span></div>`;
  $("#history").innerHTML = rows.length ? rows.map((r) => `
    <article>
      <header>
        <strong>${esc(r.intent_label)}</strong>
        ${r.escalation && r.escalation.escalate ? `<span class="tag esc">Escalated: ${esc(r.escalation.reasons[0].team)}</span>` : ""}
        ${r.faq_id ? `<span class="tag">${esc(r.faq_id)}</span>` : ""}
        ${r.secondary_intent ? `<span class="tag">Also: ${esc(r.secondary_intent)}</span>` : ""}
        ${r.compliance_status && r.compliance_status !== "pass" ? `<span class="tag flag" title="${esc((r.compliance_issues || []).join(" | "))}">Compliance flags</span>` : ""}
        <time>${esc(new Date(r.saved_at).toLocaleString())}</time>
      </header>
      <p>${esc(r.summary)}</p>
    </article>`).join("") : '<p class="empty">No saved interactions yet. Analyse a message and choose "Approve and save".</p>';
}

/* ---------- verification ---------- */
$("#run-eval").addEventListener("click", async () => {
  const btn = $("#run-eval"); btn.disabled = true; btn.textContent = "Running…";
  try {
    const r = await api("/api/evaluate", {});
    const label = { tuned: "Development set (rules built on these)", unseen: "Held-out set (new wordings)" };
    $("#metrics").innerHTML = Object.entries(r.sets).map(([name, m]) => `<p class="setlabel">${label[name] || name}: ${m.cases} messages</p>` + [
      ["Intent accuracy", m.intent_accuracy], ["FAQ top-1 accuracy", m.faq_top1_accuracy], ["FAQ top-3 recall", m.faq_top3_recall],
      ["Urgent cases caught", m.escalation_recall], ["Escalation precision", m.escalation_precision],
      ["Drafts passing compliance", m.drafts_passing_compliance],
    ].map(([k, v]) => `<div class="stat${v < 90 ? " warn" : ""}"><b>${v}%</b><span>${k}</span></div>`).join("")
      + `<div class="stat"><b>${m.avg_latency_ms} ms</b><span>Average time per message</span></div>`).join("");
    const tb = $("#eval-table tbody");
    tb.innerHTML = r.rows.map((x) => {
      const ok = x.intent_ok && x.faq_ok && x.escalation_ok;
      return `<tr><td>${x.set === "unseen" ? "Held-out" : "Dev"}</td><td>${x.id}</td><td class="msg">${esc(x.text)}</td><td>${x.expected_intent}</td>
        <td class="${x.intent_ok ? "ok" : "bad"}">${x.predicted_intent}</td><td>${x.expected_faq || "-"}</td>
        <td class="${x.faq_ok ? "ok" : "bad"}">${x.predicted_faq || "-"}</td>
        <td class="${x.escalation_ok ? "ok" : "bad"}">${x.predicted_escalation ? "yes" : "no"}</td>
        <td class="${ok ? "ok" : "bad"}">${ok ? "Pass" : "Check"}</td></tr>`;
    }).join("");
    $("#eval-table").hidden = false;
  } finally { btn.disabled = false; btn.textContent = "Run verification"; }
});

init();

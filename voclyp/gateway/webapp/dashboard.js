/* Manager dashboard: polls the public /v1 API and renders insights, provider
 * credit usage, queue depth, webhook delivery health, and stage latency.
 * Poll cadence is kept well under the per-key rate limit. */
"use strict";

const POLL_MS = 5000;
let selectedId = null;
let lastInsights = [];

function setStatus(text, cls) {
  const n = document.getElementById("dash-status");
  n.textContent = text;
  n.className = "status-line " + (cls || "muted");
}

async function refresh() {
  try {
    const [insights, metrics, webhooks] = await Promise.all([
      VoclypAPI.json("/v1/insights"),
      VoclypAPI.json("/v1/metrics"),
      VoclypAPI.json("/v1/webhooks"),
    ]);
    lastInsights = insights.insights || [];
    renderStats(lastInsights, metrics);
    renderInsights(lastInsights);
    renderUsage(metrics.provider_usage || []);
    renderDeliveries(webhooks.delivery_stats || []);
    renderLatency(metrics.stages || []);
    setStatus("live — updated " + new Date().toLocaleTimeString());
  } catch (e) {
    setStatus("✗ " + e.message, "err");
  }
}

function renderStats(insights, metrics) {
  const totalSignals = insights.reduce((n, d) => n + (d.signals || []).length, 0);
  const intents = insights.filter(
    (d) => ((d.summary || {}).fields || {}).purchase_intent).length;
  const pending = (metrics.queue || {}).pending || 0;
  const calls = (metrics.provider_usage || []).reduce((n, u) => n + u.total_calls, 0);
  const stats = [
    ["conversations", insights.length],
    ["signals extracted", totalSignals],
    ["purchase intents", intents],
    ["queue pending", pending],
    ["provider calls", calls],
  ];
  const grid = document.getElementById("stats");
  grid.textContent = "";
  for (const [label, value] of stats) {
    const s = el("div", "stat");
    s.append(el("div", "value", String(value)), el("div", "label", label));
    grid.append(s);
  }
}

function renderInsights(insights) {
  const tbody = document.getElementById("insight-rows");
  tbody.textContent = "";
  if (!insights.length) {
    const tr = el("tr"); const td = el("td", "muted", "nothing yet — submit one from the agent page");
    td.colSpan = 5; tr.append(td); tbody.append(tr);
    return;
  }
  for (const doc of insights) {
    const tr = el("tr", "clickable" + (doc.conversation_id === selectedId ? " selected" : ""));
    tr.append(el("td", null, fmtTime(doc.created_at)));
    tr.append(el("td", null, doc.agent_id || ""));
    tr.append(el("td", null, ((doc.languages || {}).detected || []).join(", ")));
    const sigTd = el("td");
    for (const [type, n] of Object.entries(countBy(doc.signals || [], "type"))) {
      sigTd.append(el("span", "pill signal-" + type, `${type} ${n}`));
    }
    tr.append(sigTd);
    tr.append(el("td", "muted", ((doc.summary || {}).text || "").slice(0, 110)));
    tr.addEventListener("click", () => { selectedId = doc.conversation_id; renderDetail(doc); renderInsights(lastInsights); });
    tbody.append(tr);
  }
}

function countBy(items, key) {
  const out = {};
  for (const it of items) out[it[key]] = (out[it[key]] || 0) + 1;
  return out;
}

function renderDetail(doc) {
  document.getElementById("detail-title").textContent =
    "Conversation " + doc.conversation_id;
  const box = document.getElementById("detail");
  box.textContent = "";

  const speakers = doc.speakers || {};
  const head = el("p");
  head.append(el("span", "pill",
    `speakers: ${speakers.count ?? "?"} (${speakers.turns ?? "?"} turns)`));
  box.append(head);

  if ((doc.transcript || []).length) {
    box.append(el("h3", null, "Transcript (redacted)"));
    const table = el("table");
    const tbody = el("tbody");
    for (const u of doc.transcript) {
      const tr = el("tr");
      tr.append(el("td", "muted", String(u.turn + 1)), el("td", null, u.speaker));
      const textTd = el("td", null, u.text);
      if (u.normalized_text && u.normalized_text !== u.text) {
        textTd.append(el("div", "quote", "→ " + u.normalized_text));
      }
      tr.append(textTd);
      tbody.append(tr);
    }
    table.append(tbody);
    box.append(table);
  }

  const fields = (doc.summary || {}).fields || {};
  box.append(el("h3", null, "Industry fields"));
  const ul = el("ul", "field-list");
  for (const [k, v] of Object.entries(fields)) {
    const li = el("li");
    li.append(el("span", "k", k + ": "), document.createTextNode(
      Array.isArray(v) ? v.join(" | ") : String(v)));
    ul.append(li);
  }
  box.append(ul);

  box.append(el("h3", null, "Signals"));
  const table = el("table");
  const tbody = el("tbody");
  for (const s of doc.signals || []) {
    const tr = el("tr");
    const typeTd = el("td");
    typeTd.append(el("span", "pill signal-" + s.type, `${s.type}/${s.subtype}`));
    tr.append(typeTd, el("td", null, s.speaker), el("td", "quote", s.quote));
    tbody.append(tr);
  }
  table.append(tbody);
  box.append(table);

  box.append(el("h3", null, "Full document (insight schema v1 — what the CRM connector will consume)"));
  box.append(el("pre", "json", JSON.stringify(doc, null, 2)));
  document.getElementById("detail-card").hidden = false;
}

function renderUsage(usage) {
  const tbody = document.getElementById("usage-rows");
  tbody.textContent = "";
  if (!usage.length) {
    const tr = el("tr"); const td = el("td", "muted", "no provider calls (stub mode is free)");
    td.colSpan = 4; tr.append(td); tbody.append(tr);
    return;
  }
  for (const u of usage) {
    const tr = el("tr");
    tr.append(el("td", null, u.endpoint), el("td", null, String(u.total_calls)),
              el("td", null, String(u.conversations)), el("td", null, String(u.avg_calls_per_conversation)));
    tbody.append(tr);
  }
}

function renderDeliveries(stats) {
  const tbody = document.getElementById("delivery-rows");
  tbody.textContent = "";
  for (const d of stats) {
    const tr = el("tr");
    tr.append(el("td", null, d.url), el("td", null, d.endpoint_status),
              el("td", null, String(d.delivered)), el("td", null, String(d.dlq_depth)),
              el("td", null, Math.round((d.success_rate || 0) * 100) + "%"));
    tbody.append(tr);
  }
}

function renderLatency(stages) {
  const tbody = document.getElementById("latency-rows");
  tbody.textContent = "";
  for (const s of stages) {
    const tr = el("tr");
    tr.append(el("td", null, s.stage), el("td", null, String(s.conversations)),
              el("td", null, String(s.avg_ms)), el("td", null, String(s.max_ms)));
    tbody.append(tr);
  }
}

refresh();
setInterval(refresh, POLL_MS);

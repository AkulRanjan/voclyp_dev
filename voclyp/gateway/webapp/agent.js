/* Field-agent page: consent gate, in-browser WAV recording (or typed
 * transcript for stub mode), upload through the gateway, then poll until the
 * insight is ready and render it. Talks ONLY to the public /v1 API. */
"use strict";

const TARGET_RATE = 16000; // what Saarika ASR expects; also keeps uploads small

const consent = document.getElementById("consent");
const recBtn = document.getElementById("rec-btn");
const recTimer = document.getElementById("rec-timer");
const recPreview = document.getElementById("rec-preview");
const submitBtn = document.getElementById("submit-btn");
const submitStatus = document.getElementById("submit-status");
const resultCard = document.getElementById("result-card");

let mode = "record";
let wavBlob = null;
let recorder = null; // {stream, ctx, source, proc, chunks, sampleRate, startedAt, tick}

// ---- tabs -----------------------------------------------------------------
function setMode(m) {
  mode = m;
  document.getElementById("tab-record").classList.toggle("active", m === "record");
  document.getElementById("tab-text").classList.toggle("active", m === "text");
  document.getElementById("pane-record").hidden = m !== "record";
  document.getElementById("pane-text").hidden = m !== "text";
  refreshButtons();
}
document.getElementById("tab-record").addEventListener("click", () => setMode("record"));
document.getElementById("tab-text").addEventListener("click", () => setMode("text"));

function refreshButtons() {
  recBtn.disabled = !consent.checked;
  // Never leave the user staring at a silently disabled button — say why.
  let why = "";
  if (!VoclypAPI.key()) why = "no API key saved — set it on the home page first";
  else if (!consent.checked) why = "tick the consent box (step 1) to enable submission";
  else if (recorder) why = "stop the recording first";
  else if (mode === "record" && !wavBlob) why = "record something first — or use the transcript tab (free in stub mode)";
  else if (mode === "text" && !document.getElementById("transcript").value.trim()) why = "transcript is empty";
  submitBtn.disabled = !!why;
  if (why) setStatus(why);
  else if (!submitStatus.classList.contains("ok")) setStatus("ready to upload");
}
consent.addEventListener("change", refreshButtons);
document.getElementById("transcript").addEventListener("input", refreshButtons);

// ---- WAV recording ----------------------------------------------------------
// MediaRecorder produces webm/opus, which the ASR providers don't take; instead
// capture raw PCM via Web Audio and encode a 16 kHz mono 16-bit WAV ourselves.
async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const source = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  proc.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  source.connect(proc);
  proc.connect(ctx.destination); // required by some browsers for the node to fire
  const startedAt = Date.now();
  const tick = setInterval(() => {
    const s = Math.floor((Date.now() - startedAt) / 1000);
    recTimer.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 250);
  recorder = { stream, ctx, source, proc, chunks, sampleRate: ctx.sampleRate, startedAt, tick };
}

function stopRecording() {
  const r = recorder;
  recorder = null;
  clearInterval(r.tick);
  r.proc.disconnect(); r.source.disconnect();
  r.stream.getTracks().forEach((t) => t.stop());
  r.ctx.close();

  let total = 0;
  for (const c of r.chunks) total += c.length;
  const all = new Float32Array(total);
  let off = 0;
  for (const c of r.chunks) { all.set(c, off); off += c.length; }

  wavBlob = encodeWav(downsample(all, r.sampleRate, TARGET_RATE), TARGET_RATE);
  recPreview.src = URL.createObjectURL(wavBlob);
  recPreview.hidden = false;
}

function downsample(samples, fromRate, toRate) {
  if (toRate >= fromRate) return samples;
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(samples.length / ratio));
  for (let i = 0; i < out.length; i++) {
    // average the source window — cheap anti-aliasing, fine for speech
    const start = Math.floor(i * ratio), end = Math.min(Math.floor((i + 1) * ratio), samples.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += samples[j];
    out[i] = sum / (end - start || 1);
  }
  return out;
}

function encodeWav(samples, sampleRate) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

recBtn.addEventListener("click", async () => {
  try {
    if (recorder) {
      stopRecording();
      recBtn.textContent = "⏺ Record again";
      recBtn.classList.remove("recording");
    } else {
      wavBlob = null;
      recPreview.hidden = true;
      await startRecording();
      recBtn.textContent = "⏹ Stop";
      recBtn.classList.add("recording");
      recTimer.textContent = "00:00";
    }
  } catch (e) {
    setStatus("microphone unavailable: " + e.message + " (use localhost/https, or the transcript tab)", "err");
  }
  refreshButtons();
});

// ---- submit + poll ----------------------------------------------------------
function setStatus(text, cls) {
  submitStatus.textContent = text;
  submitStatus.className = "status-line " + (cls || "");
}

submitBtn.addEventListener("click", async () => {
  const body = mode === "record"
    ? wavBlob
    : new Blob([document.getElementById("transcript").value], { type: "text/plain" });
  const form = new FormData();
  form.append("audio", body, mode === "record" ? "recording.wav" : "transcript.txt");
  form.append("agent_id", document.getElementById("agent-id").value || "agent-001");
  form.append("client_ref", "web-" + crypto.randomUUID());
  form.append("consent_captured", consent.checked ? "true" : "false");
  form.append("customer_name", document.getElementById("customer-name").value);

  submitBtn.disabled = true;
  resultCard.hidden = true;
  try {
    setStatus("uploading…");
    const out = await VoclypAPI.json("/v1/conversations", { method: "POST", body: form });
    setStatus(`queued as ${out.conversation_id} — processing…`);
    await pollInsight(out.conversation_id);
  } catch (e) {
    setStatus("✗ " + e.message, "err");
  }
  submitBtn.disabled = false;
});

async function pollInsight(id) {
  for (let i = 0; i < 90; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const doc = await VoclypAPI.json("/v1/insights/" + id);
      setStatus("✓ insight ready (audio destroyed)", "ok");
      renderInsight(doc);
      return;
    } catch (e) {
      if (e.status !== 404) throw e;
      setStatus(`processing… (${(i + 1) * 2}s — is the worker running?)`);
    }
  }
  throw new Error("timed out waiting for the insight");
}

function transcriptTable(transcript) {
  const table = el("table");
  const tbody = el("tbody");
  for (const u of transcript) {
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
  return table;
}

function renderInsight(doc) {
  const box = document.getElementById("result");
  box.textContent = "";

  const langs = doc.languages || {};
  const speakers = doc.speakers || {};
  const head = el("p");
  head.append(
    el("span", "pill", "languages: " + (langs.detected || []).join(", ")),
    el("span", "pill", langs.code_switching ? "code-switching" : "single language"),
    el("span", "pill", `speakers: ${speakers.count ?? "?"} (${speakers.turns ?? "?"} turns)`),
    el("span", "pill", `signals: ${(doc.signals || []).length}`),
    el("span", "pill", `redactions: ${Object.entries((doc.privacy || {}).pii_redactions || {})
      .map(([k, n]) => `${k}×${n}`).join(" ") || "none"}`),
  );
  box.append(head);

  box.append(el("h3", null, "Summary"));
  box.append(el("p", null, (doc.summary || {}).text || ""));

  if ((doc.transcript || []).length) {
    box.append(el("h3", null, "Transcript (redacted — the audio itself is destroyed)"));
    box.append(transcriptTable(doc.transcript));
  }

  box.append(el("h3", null, "Signals"));
  const table = el("table");
  const thead = el("thead"); const hr = el("tr");
  for (const h of ["type", "subtype", "speaker", "quote"]) hr.append(el("th", null, h));
  thead.append(hr); table.append(thead);
  const tbody = el("tbody");
  for (const s of doc.signals || []) {
    const tr = el("tr");
    const typeTd = el("td");
    typeTd.append(el("span", "pill signal-" + s.type, s.type));
    tr.append(typeTd, el("td", null, s.subtype), el("td", null, s.speaker),
              el("td", "quote", s.quote));
    tbody.append(tr);
  }
  table.append(tbody);
  box.append(table);

  box.append(el("h3", null, "Privacy & audit"));
  const ul = el("ul", "field-list");
  const audit = doc.audit || {};
  ul.append(el("li", null, `audio destroyed at: ${audit.audio_deleted_at || "?"}`));
  ul.append(el("li", null, `consent captured: ${((doc.privacy || {}).consent_captured) ? "yes" : "no"}`));
  ul.append(el("li", null, `pipeline: ${Object.entries(audit.stage_versions || {})
    .map(([k, v]) => `${k}=${v}`).join(", ")}`));
  box.append(ul);

  resultCard.hidden = false;
  resultCard.scrollIntoView({ behavior: "smooth" });
}

setMode("record");
refreshButtons();

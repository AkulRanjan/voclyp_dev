import { useMemo, useState } from "react";
import { Button } from "../components/Button";
import { Icon } from "../components/Icon";
import { getApiKey } from "../data/api";
import { insightToPitchRow } from "../data/voclypAdapter";
import type { InsightDoc } from "../data/api";
import { PitchDrawer } from "../manager/pitches/PitchDrawer";
import type { PitchRow } from "../data/types";
import { useRecorder } from "./useRecorder";
import { secondsToClock } from "../lib/format";
import "./field.css";

type Status = { kind: "idle" | "busy" | "ok" | "err"; text: string };

// Salesperson interface: capture consent, record the visit, submit it to the
// VoClyp gateway, then show the resulting pitch insight in the same drawer the
// manager sees — closing the loop end to end.
export function FieldRecorderPage() {
  const { recording, elapsed, wav, error, start, stop, reset } = useRecorder();
  const [consent, setConsent] = useState(false);
  const [customer, setCustomer] = useState("");
  const [agentId, setAgentId] = useState("agent-001");
  const [status, setStatus] = useState<Status>({ kind: "idle", text: "" });
  const [result, setResult] = useState<PitchRow | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const canSubmit = consent && wav !== null && !recording && status.kind !== "busy";

  const hint = useMemo(() => {
    if (!getApiKey()) return "Set the gateway API key in Settings before submitting.";
    if (!consent) return "Tick consent to enable recording.";
    if (!wav && !recording) return "Record the visit, then submit.";
    return "";
  }, [consent, wav, recording]);

  async function submit() {
    if (!wav) return;
    setResult(null);
    setStatus({ kind: "busy", text: "Uploading…" });
    const form = new FormData();
    form.append("audio", wav, "recording.wav");
    form.append("agent_id", agentId || "agent-001");
    form.append("client_ref", "web-" + crypto.randomUUID());
    form.append("consent_captured", "true");
    form.append("customer_name", customer);
    try {
      const resp = await fetch("/v1/conversations", {
        method: "POST",
        headers: { "X-API-Key": getApiKey() },
        body: form,
      });
      if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || resp.statusText);
      const { conversation_id } = (await resp.json()) as { conversation_id: string };
      setStatus({ kind: "busy", text: `Queued ${conversation_id} — processing…` });
      await poll(conversation_id);
    } catch (e) {
      setStatus({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    }
  }

  async function poll(id: string) {
    for (let i = 0; i < 90; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const resp = await fetch("/v1/insights/" + id, { headers: { "X-API-Key": getApiKey() } });
      if (resp.status === 200) {
        const doc = (await resp.json()) as InsightDoc;
        setResult(insightToPitchRow(doc));
        setDrawerOpen(true);
        setStatus({ kind: "ok", text: "Insight ready — audio destroyed." });
        reset();
        return;
      }
      if (resp.status !== 404) {
        setStatus({ kind: "err", text: "Error " + resp.status });
        return;
      }
      setStatus({ kind: "busy", text: `Processing… (${(i + 1) * 2}s — is the worker running?)` });
    }
    setStatus({ kind: "err", text: "Timed out waiting for the insight." });
  }

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Record a visit</h1>
          <p className="page__subtitle">Captured audio flows into VoClyp and becomes a pitch insight</p>
        </div>
      </div>

      <div className="field-grid">
        <div className="field-card">
          <h3 className="field-card__title">1 · Consent &amp; details</h3>
          <label className="field-check">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            Customer consents to this conversation being recorded and analyzed
          </label>
          <div className="field-row">
            <input
              className="field-input"
              placeholder="Customer name (redacted from insights)"
              value={customer}
              onChange={(e) => setCustomer(e.target.value)}
            />
            <input
              className="field-input"
              placeholder="Agent id"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
            />
          </div>
        </div>

        <div className="field-card">
          <h3 className="field-card__title">2 · Record</h3>
          <div className="field-rec">
            <button
              className={`field-recbtn${recording ? " is-rec" : ""}`}
              disabled={!consent}
              onClick={() => (recording ? stop() : void start())}
            >
              <Icon name={recording ? "pause" : "mic"} size={20} />
              {recording ? "Stop" : wav ? "Re-record" : "Record"}
            </button>
            <span className="field-timer">{secondsToClock(elapsed)}</span>
          </div>
          {wav && !recording && (
            <audio className="field-preview" controls src={URL.createObjectURL(wav)} />
          )}
          {error && <p className="field-msg field-msg--err">{error}</p>}
        </div>

        <div className="field-card">
          <h3 className="field-card__title">3 · Submit</h3>
          <div className="field-submit">
            <Button variant="primary" disabled={!canSubmit} onClick={() => void submit()}>
              Upload &amp; process
            </Button>
            <span className={`field-msg field-msg--${status.kind}`}>
              {status.text || hint}
            </span>
          </div>
        </div>
      </div>

      {result && (
        <div className="field-result">
          <p className="field-result__note">
            ✓ This visit was analyzed by VoClyp. Open the pitch insight:
          </p>
          <Button variant="outline" onClick={() => setDrawerOpen(true)}>
            View pitch insight
          </Button>
        </div>
      )}

      <PitchDrawer row={drawerOpen ? result : null} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}

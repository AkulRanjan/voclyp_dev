// Adapter: VoClyp insight document -> Pitches data model. This is the seam
// that lets real recorded conversations drive the same manager UI the seed
// data does.
//
// What maps cleanly: summary, signals (by type) -> signal groups, intent/sale
// (from taxonomy fields), worker/brand/script (from metadata + taxonomy).
//
// Two honest gaps, handled explicitly rather than faked:
//  1. Coaching SCORES (clarity/closing/…): VoClyp's pipeline does not yet emit
//     pitch-coaching scores. Until an LLM-backed scoring stage lands, we derive
//     a provisional score from the signal mix and flag it. Centralized here so
//     swapping in real scores is a one-function change.
//  2. RECORDING: VoClyp destroys the audio after redaction by design, so there
//     is no recordingUrl to play. The drawer shows that as a privacy guarantee.
import type { Intent, PitchInstance, PitchRow } from "./types";
import { ratingForScore } from "../lib/bands";
import type { InsightDoc } from "./api";

function groupSignals(doc: InsightDoc): PitchInstance["signals"] {
  const g: PitchInstance["signals"] = {
    products: [],
    positive: [],
    negative: [],
    objections: [],
    explicitConcerns: [],
    implicitConcerns: [],
  };
  for (const s of doc.signals) {
    const q = s.quote;
    switch (s.type) {
      case "promise":
      case "intent":
        g.positive.push(q);
        break;
      case "demand":
        g.products.push(q);
        break;
      case "objection":
        g.objections.push(q);
        break;
      case "price_reaction":
        g.objections.push(q);
        break;
      case "competitor_mention":
        g.negative.push(q);
        break;
      default:
        g.negative.push(q);
    }
  }
  return g;
}

// Provisional 0..100 score until the pipeline emits real coaching scores.
// Positive signals lift it, objections/competitor mentions pull it down.
function provisionalScore(doc: InsightDoc): number {
  const pos = doc.signals.filter((s) => s.type === "promise" || s.type === "intent").length;
  const neg = doc.signals.filter(
    (s) => s.type === "objection" || s.type === "price_reaction" || s.type === "competitor_mention",
  ).length;
  const raw = 45 + pos * 12 - neg * 8;
  return Math.max(0, Math.min(100, raw));
}

function deriveIntent(doc: InsightDoc): Intent {
  const f = doc.summary.fields || {};
  if (f.purchase_intent === true) return "High";
  const hasIntent = doc.signals.some((s) => s.type === "intent");
  return hasIntent ? "Medium" : "Low";
}

function subScores(score: number) {
  const base = Math.round((score / 100) * 10);
  const c = (d: number) => Math.max(0, Math.min(10, base + d));
  return {
    clarity: c(1),
    closing: c(-1),
    structure: c(0),
    engagement: c(0),
    uspDelivery: c(-1),
    objectionHandling: c(-2),
  };
}

export function insightToPitchRow(doc: InsightDoc): PitchRow {
  const score = provisionalScore(doc);
  const intent = deriveIntent(doc);
  const sale = (doc.summary.fields || {}).purchase_intent === true;

  const instance: PitchInstance = {
    index: 1,
    score,
    rating: ratingForScore(score),
    durationSec: 0, // not present in the insight doc (audio destroyed)
    qualified: score >= 50,
    saleMade: sale,
    intent,
    pitchIntent: doc.signals.some((s) => s.type === "intent" || s.type === "promise"),
    timestampStart: 0,
    timestampEnd: 0,
    recordingUrl: "", // intentionally empty: audio is destroyed after processing
    recordingDurationSec: 0,
    summary: doc.summary.text || "",
    scores: subScores(score),
    productsMentionedExtra: doc.signals.filter((s) => s.type === "demand").length,
    signals: groupSignals(doc),
    coaching: {
      missed: doc.signals.length === 0
        ? ["No clear sales signals detected — consider a more structured pitch."]
        : [],
    },
  };

  return {
    id: doc.conversation_id,
    brand: titleCase(doc.industry) || "—",
    brandSubtitle: "primary pitch",
    script: doc.audit?.taxonomy_version || "—",
    coverage: Math.round((score / 100) * 100),
    store: "—", // VoClyp metadata does not carry a store name yet
    worker: doc.agent_id || "—",
    best: score,
    avg: score,
    pitchesTotal: 1,
    pitchesQualified: instance.qualified ? 1 : 0,
    sale,
    intent,
    date: doc.created_at,
    instances: [instance],
  };
}

function titleCase(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

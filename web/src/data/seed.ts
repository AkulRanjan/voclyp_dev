// Seed data for the Pitches list. The first row's Instance #1 reproduces the
// detail-drawer example from the spec exactly; the rest are generated with
// band-appropriate content. Swap this module for the VoClyp adapter
// (voclypAdapter.ts) to drive the same UI from real insight documents.
import type { Intent, PitchInstance, PitchRow, PitchScores } from "./types";
import { ratingForScore } from "../lib/bands";

function scoresForBand(score: number): PitchScores {
  // Spread the 0..100 score across the six 0..10 sub-scores with mild variation
  // so the bars don't all read identically. The row-1 example overrides these.
  const base = Math.round((score / 100) * 10);
  const j = (d: number) => Math.max(0, Math.min(10, base + d));
  return {
    clarity: j(1),
    closing: j(-1),
    structure: j(0),
    engagement: j(0),
    uspDelivery: j(-1),
    objectionHandling: j(-2),
  };
}

const STRONG_SUMMARY =
  "The agent opened with a clear introduction of Mr.Makhana and connected the " +
  "product's health positioning to the store's customer base. Pricing and the " +
  "current scheme were covered, an objection about margin was addressed, and the " +
  "conversation closed with a concrete next step.";

const WEAK_SUMMARY =
  "The conversation includes a brief mention of makhana/snacks, but it does not " +
  "develop into a clear sales pitch for Mr.Makhana. Most of the exchange is about " +
  "customer footfall, timing, and store location rather than product benefits or a " +
  "direct recommendation.";

function makeInstance(
  index: number,
  score: number,
  intent: Intent,
  sale: boolean,
  qualified: boolean,
  startSec: number,
): PitchInstance {
  const good = score >= 50;
  const dur = good ? 132 : 78 + index * 9;
  return {
    index,
    score,
    rating: ratingForScore(score),
    durationSec: dur,
    qualified,
    saleMade: sale,
    intent,
    pitchIntent: good,
    timestampStart: startSec,
    timestampEnd: startSec + dur,
    recordingUrl: "",
    recordingDurationSec: dur,
    summary: good ? STRONG_SUMMARY : WEAK_SUMMARY,
    scores: scoresForBand(score),
    productsMentionedExtra: good ? 6 : 3,
    signals: good
      ? {
          products: ["makhana", "snacks", "roasted makhana"],
          positive: [
            "Customer acknowledged product fit for the store",
            "Discussed health positioning and target shoppers",
            "Agreed to stock a trial quantity",
          ],
          negative: ["Closing could have confirmed order size sooner"],
          objections: ["Margin compared to competing brand"],
          explicitConcerns: ["Shelf space is limited"],
          implicitConcerns: ["Unsure about repeat demand"],
        }
      : {
          products: ["makhana", "snacks"],
          positive: [
            "Customer acknowledged seeing makhana/snacks",
            "Discussion of evening sales timing",
          ],
          negative: [
            "No clear product pitch",
            "No direct brand recommendation",
            "Conversation focused on store operations and footfall",
          ],
          objections: [
            "No customers at this time",
            "No samples right now",
            "Store traffic is low during the day",
          ],
          explicitConcerns: ["Low customer traffic", "No samples available"],
          implicitConcerns: ["Product may not be actively promoted in-store"],
        },
    coaching: {
      missed: good
        ? [
            "Could have asked for a larger opening order while interest was high.",
            "Could have scheduled a follow-up visit to review sell-through.",
          ]
        : [
            "Could have introduced Mr.Makhana clearly and explained its health benefits.",
            "Could have used the low-footfall moment to offer a sample or quick product demo.",
          ],
    },
  };
}

// The exact Instance #1 from the spec (Images 1 & 2).
const MEWA_MART_INSTANCE_1: PitchInstance = {
  index: 1,
  score: 31,
  rating: "Poor",
  durationSec: 87,
  qualified: false,
  saleMade: false,
  intent: "Low",
  pitchIntent: false,
  timestampStart: 300.5,
  timestampEnd: 387.7,
  recordingUrl: "",
  recordingDurationSec: 87,
  summary: WEAK_SUMMARY,
  scores: {
    clarity: 4,
    closing: 2,
    structure: 3,
    engagement: 3,
    uspDelivery: 2,
    objectionHandling: 1,
  },
  productsMentionedExtra: 3,
  signals: {
    products: ["makhana", "snacks"],
    positive: [
      "Customer acknowledged seeing makhana/snacks",
      "Discussion of evening sales timing",
    ],
    negative: [
      "No clear product pitch",
      "No direct brand recommendation",
      "Conversation focused on store operations and footfall",
    ],
    objections: [
      "No customers at this time",
      "No samples right now",
      "Store traffic is low during the day",
    ],
    explicitConcerns: ["Low customer traffic", "No samples available"],
    implicitConcerns: ["Product may not be actively promoted in-store"],
  },
  coaching: {
    missed: [
      "Could have introduced Mr.Makhana clearly and explained its health benefits.",
      "Could have used the low-footfall moment to offer a sample or quick product demo.",
    ],
  },
};

interface SeedSpec {
  script: string;
  coverage: number;
  store: string;
  worker: string;
  best: number;
  avg: number;
  total: number;
  qualified: number;
  sale: boolean;
  intent: Intent;
  date: string; // ISO
}

const SPECS: SeedSpec[] = [
  { script: "Pitch Alpha v1", coverage: 0,  store: "Mewa mart",             worker: "NIRMALA RAWAT", best: 31, avg: 31, total: 1, qualified: 0, sale: false, intent: "Low",    date: "2026-06-12" },
  { script: "Pitch Alpha v1", coverage: 0,  store: "Raj store",             worker: "Sangitha",      best: 28, avg: 28, total: 1, qualified: 0, sale: false, intent: "Low",    date: "2026-06-12" },
  { script: "Pitch Alpha v1", coverage: 80, store: "12ve and 12ve",         worker: "Sangitha",      best: 68, avg: 67, total: 2, qualified: 2, sale: true,  intent: "Medium", date: "2026-06-12" },
  { script: "Pitch Gamma v1", coverage: 78, store: "(vera paneer)",         worker: "NIRMALA RAWAT", best: 68, avg: 68, total: 1, qualified: 1, sale: true,  intent: "Medium", date: "2026-06-12" },
  { script: "Pitch Gamma v1", coverage: 63, store: "Maxims",                worker: "Sangitha",      best: 58, avg: 58, total: 1, qualified: 1, sale: true,  intent: "Medium", date: "2026-06-11" },
  { script: "Pitch Gamma v1", coverage: 63, store: "The New Shop Pagarganj", worker: "NIRMALA RAWAT", best: 68, avg: 68, total: 1, qualified: 1, sale: true,  intent: "Medium", date: "2026-06-11" },
  { script: "Pitch Alpha v1", coverage: 78, store: "Saver bazar",           worker: "Sangitha",      best: 53, avg: 53, total: 1, qualified: 1, sale: true,  intent: "Medium", date: "2026-06-11" },
  { script: "Pitch Alpha v1", coverage: 0,  store: "Juneja confectionery",  worker: "Sangitha",      best: 12, avg: 12, total: 1, qualified: 0, sale: false, intent: "Low",    date: "2026-06-11" },
  { script: "Pitch Beta v1",  coverage: 0,  store: "New shop 24 adchini",   worker: "NIRMALA RAWAT", best: 4,  avg: 4,  total: 1, qualified: 0, sale: false, intent: "Low",    date: "2026-06-10" },
];

function buildInstances(spec: SeedSpec, rowIndex: number): PitchInstance[] {
  // Row 1 carries the exact spec example as its single instance.
  if (rowIndex === 0) return [MEWA_MART_INSTANCE_1];

  const out: PitchInstance[] = [];
  for (let i = 0; i < spec.total; i++) {
    const score = i === 0 ? spec.best : Math.max(0, spec.avg - 2);
    out.push(
      makeInstance(
        i + 1,
        score,
        spec.intent,
        spec.sale,
        i < spec.qualified,
        120 + i * 95,
      ),
    );
  }
  return out;
}

export const SEED_PITCHES: PitchRow[] = SPECS.map((spec, i) => ({
  id: `pitch-${i + 1}`,
  brand: "Mr.Makhana",
  brandSubtitle: "primary pitch",
  script: spec.script,
  coverage: spec.coverage,
  store: spec.store,
  worker: spec.worker,
  best: spec.best,
  avg: spec.avg,
  pitchesTotal: spec.total,
  pitchesQualified: spec.qualified,
  sale: spec.sale,
  intent: spec.intent,
  date: spec.date,
  instances: buildInstances(spec, i),
}));

// Distinct values for the filter dropdowns, derived from the data.
export function distinct<T>(items: T[], pick: (t: T) => string): string[] {
  return Array.from(new Set(items.map(pick))).sort();
}

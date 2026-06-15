// The Pitches data model. A PitchRow is one (brand × script × store × worker)
// pitch record in the list; it holds one or more PitchInstance recordings that
// open in the detail drawer.

export type Intent = "Low" | "Medium" | "High";

export type Rating = "Poor" | "Average" | "Good";

export interface PitchScores {
  clarity: number;
  closing: number;
  structure: number;
  engagement: number;
  uspDelivery: number;
  objectionHandling: number;
}

export interface PitchSignals {
  products: string[];
  positive: string[];
  negative: string[];
  objections: string[];
  explicitConcerns: string[];
  implicitConcerns: string[];
}

export interface PitchInstance {
  index: number; // "Instance #1"
  score: number; // 31
  rating: Rating; // derived from the score band
  durationSec: number; // 87
  qualified: boolean;
  saleMade: boolean;
  intent: Intent;
  pitchIntent: boolean;
  timestampStart: number; // 300.5
  timestampEnd: number; // 387.7
  recordingUrl: string;
  recordingDurationSec: number; // 87 -> "1:27"
  summary: string;
  scores: PitchScores;
  productsMentionedExtra: number; // the "+3"
  signals: PitchSignals;
  coaching: { missed: string[] };
}

export interface PitchRow {
  id: string;
  brand: string; // "Mr.Makhana"
  brandSubtitle: string; // "primary pitch"
  script: string; // "Pitch Alpha v1"
  coverage: number; // 0..100
  store: string;
  worker: string;
  best: number;
  avg: number;
  pitchesTotal: number;
  pitchesQualified: number;
  sale: boolean;
  intent: Intent;
  date: string; // ISO; displayed as "12 Jun 26"
  instances: PitchInstance[];
}

// Column keys that the list can sort on.
export type SortKey = "brand" | "date";
export type SortDir = "asc" | "desc";

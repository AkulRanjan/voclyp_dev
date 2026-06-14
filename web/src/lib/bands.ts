// Score -> band mapping, centralized so the list badge and the drawer badge
// always agree. Scores are 0..100 (BEST/AVG and the instance score).
import type { Rating, Intent } from "../data/types";

export type Tone = "red" | "amber" | "green" | "gray";

export interface Band {
  rating: Rating;
  tone: Tone;
}

const POOR_MAX = 40; // < 40  -> Poor
const AVERAGE_MAX = 65; // 40..64 -> Average, >= 65 -> Good

export function scoreBand(score: number): Band {
  if (score < POOR_MAX) return { rating: "Poor", tone: "red" };
  if (score < AVERAGE_MAX) return { rating: "Average", tone: "amber" };
  return { rating: "Good", tone: "green" };
}

/** Derive the rating label directly (e.g. for seed data construction). */
export function ratingForScore(score: number): Rating {
  return scoreBand(score).rating;
}

// Intent shares the same neutral/amber/green language as score bands.
export function intentTone(intent: Intent): Tone {
  switch (intent) {
    case "High":
      return "green";
    case "Medium":
      return "amber";
    case "Low":
    default:
      return "gray";
  }
}

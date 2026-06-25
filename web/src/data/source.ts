// Data-source switch: the same Pitches UI runs on seed data or on live VoClyp
// insights. Preference is stored in the browser and toggled in Settings.
import type { PitchRow } from "./types";
import { SEED_PITCHES } from "./seed";
import { fetchInsights } from "./api";
import { insightToPitchRow } from "./voclypAdapter";

export type DataSource = "seed" | "live";

const STORAGE = "voclyp_data_source";

export function getDataSource(): DataSource {
  if (localStorage.getItem(STORAGE) === "seed") return "seed";
  return "live";
}

export function setDataSource(src: DataSource): void {
  localStorage.setItem(STORAGE, src);
}

export async function loadPitches(source: DataSource): Promise<PitchRow[]> {
  if (source === "live") {
    const docs = await fetchInsights();
    return docs.map(insightToPitchRow);
  }
  return SEED_PITCHES;
}

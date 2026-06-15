// Client for the VoClyp gateway's /v1 API. Console users authenticate with
// their session token (Authorization: Bearer) — the same credential that gates
// the UI — so the server enforces their role's scopes. No separate API key is
// stored in the browser. In dev, Vite proxies /v1 to the gateway.
import { authHeaders } from "./auth";

export async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(path, { headers: authHeaders() });
  if (resp.status === 401) throw new Error("session expired — sign in again");
  if (resp.status === 403) throw new Error("not permitted for your role");
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail || detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

// The subset of the VoClyp insight document the adapter consumes.
export interface InsightDoc {
  conversation_id: string;
  industry: string;
  agent_id: string;
  created_at: string;
  languages: { detected: string[]; normalized_to: string; code_switching: boolean };
  speakers?: { count: number; turns: number };
  transcript?: { turn: number; speaker: string; text: string; normalized_text?: string }[];
  signals: { type: string; subtype: string; speaker: string; quote: string }[];
  summary: { text: string; fields: Record<string, unknown> };
  privacy: { consent_captured: boolean; pii_redactions: Record<string, number> };
  audit: { audio_deleted_at: string | null; taxonomy_version?: string };
}

export async function fetchInsights(): Promise<InsightDoc[]> {
  const data = await apiGet<{ insights: InsightDoc[] }>("/v1/insights");
  return data.insights || [];
}

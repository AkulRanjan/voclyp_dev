import { useEffect, useState } from "react";
import { authHeaders } from "./auth";

export interface ActiveSession {
  session_id: string;
  store_id: string;
  store_name: string;
  agent_id: string;
  status: string;
  customer_name: string | null;
  customer_phone: string | null;
  started_at: string;
  consent_at: string | null;
}

export function useLiveSessions(pollMs = 5000) {
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const resp = await fetch("/v1/sessions/active", { headers: authHeaders() });
        if (!resp.ok) throw new Error(await resp.text());
        const data = (await resp.json()) as { sessions: ActiveSession[] };
        if (!cancelled) setSessions(data.sessions);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    };
    void load();
    const t = setInterval(load, pollMs);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [pollMs]);

  return { sessions, error };
}

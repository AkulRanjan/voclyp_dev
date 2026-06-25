import { useEffect, useState } from "react";
import { authHeaders } from "./auth";

export interface StoreMetrics {
  store_id: string;
  store_name: string;
  visits: number;
  qualified_pct: number;
  orthopaedic_demand_pct: number;
  competitor_mentions: number;
  trial_requests: number;
  emi_requests: number;
  top_objection: string | null;
  vs_area_avg_visits?: number;
}

export function useStoreAnalytics(areaId?: string) {
  const [stores, setStores] = useState<StoreMetrics[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const q = areaId ? `?area_id=${encodeURIComponent(areaId)}` : "";
    fetch(`/v1/analytics/stores/compare${q}`, { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      })
      .then((data: { stores: StoreMetrics[] }) => {
        if (!cancelled) setStores(data.stores);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [areaId]);

  return { stores, loading, error };
}

export interface AreaSummary {
  area_id: string | null;
  stores: number;
  visits: number;
  qualified_pct: number;
  avg_score: number;
  top_store: { store_id: string; store_name: string; qualified_pct: number } | null;
  needs_attention:
    | { store_id: string; store_name: string; qualified_pct: number }
    | null;
}

export interface RepRow {
  agent_id: string;
  name: string;
  visits: number;
  avg_score: number;
  win_rate: number;
  at_risk: number;
  top_objection: string | null;
}

export function useAreaSummary(areaId?: string) {
  const [summary, setSummary] = useState<AreaSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const q = areaId ? `?area_id=${encodeURIComponent(areaId)}` : "";
    fetch(`/v1/analytics/summary${q}`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((data: AreaSummary) => {
        if (!cancelled) setSummary(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [areaId]);

  return { summary, loading };
}

export function useRepLeaderboard(areaId?: string) {
  const [reps, setReps] = useState<RepRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const q = areaId ? `?area_id=${encodeURIComponent(areaId)}` : "";
    fetch(`/v1/analytics/reps${q}`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((data: { reps: RepRow[] }) => {
        if (!cancelled) setReps(data.reps);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [areaId]);

  return { reps, loading };
}

export function useStoreDetail(storeId: string) {
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`/v1/analytics/stores/${encodeURIComponent(storeId)}`, {
      headers: authHeaders(),
    })
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storeId]);

  return { detail, loading };
}

function maskPhone(phone: string | null | undefined): string {
  if (!phone) return "—";
  const d = phone.replace(/\D/g, "");
  if (d.length < 4) return "••••";
  return `••••${d.slice(-4)}`;
}

export { maskPhone };

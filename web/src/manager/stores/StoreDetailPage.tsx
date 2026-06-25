import { Link, useParams } from "react-router-dom";
import { useStoreDetail } from "../../data/useStoreAnalytics";
import "./stores.css";

export function StoreDetailPage() {
  const { storeId = "" } = useParams();
  const { detail, loading } = useStoreDetail(storeId);

  if (loading) return <p className="stores-muted">Loading store…</p>;
  if (!detail) return <p className="stores-error">Store not found</p>;

  const store = detail.store as { name: string; store_id: string; address?: string };
  const metrics = detail.metrics as Record<string, number | string | null>;
  const recent = (detail.recent_visits as Array<{
    conversation_id: string;
    summary: string;
    created_at: string;
    signal_count: number;
  }>) || [];

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <Link to="/manager/stores" className="stores-back">
            ← All stores
          </Link>
          <h1 className="page__title">{store.name}</h1>
          <p className="page__subtitle">{store.address || store.store_id}</p>
        </div>
      </div>

      <div className="store-stats">
        <div className="store-stat">
          <div className="store-stat__val">{metrics.visits ?? 0}</div>
          <div className="store-stat__lbl">Visits</div>
        </div>
        <div className="store-stat">
          <div className="store-stat__val">{metrics.qualified_pct ?? 0}%</div>
          <div className="store-stat__lbl">Qualified</div>
        </div>
        <div className="store-stat">
          <div className="store-stat__val">{metrics.orthopaedic_demand_pct ?? 0}%</div>
          <div className="store-stat__lbl">Ortho demand</div>
        </div>
        <div className="store-stat">
          <div className="store-stat__val">{metrics.competitor_mentions ?? 0}</div>
          <div className="store-stat__lbl">Competitor mentions</div>
        </div>
      </div>

      <h2 className="stores-section-title">Recent visits</h2>
      <div className="visit-list">
        {recent.length === 0 ? (
          <p className="stores-muted">No visits recorded yet.</p>
        ) : (
          recent.map((v) => (
            <article key={v.conversation_id} className="visit-card">
              <p className="visit-card__summary">{v.summary || "Visit recorded"}</p>
              <p className="visit-card__meta">
                {v.signal_count} signals · {new Date(v.created_at).toLocaleString()}
              </p>
            </article>
          ))
        )}
      </div>
    </div>
  );
}

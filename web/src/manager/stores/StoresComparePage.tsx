import { Link } from "react-router-dom";
import {
  useAreaSummary,
  useRepLeaderboard,
  useStoreAnalytics,
} from "../../data/useStoreAnalytics";
import "../stores/stores.css";

export function StoresComparePage() {
  const { stores, loading, error } = useStoreAnalytics();
  const { summary } = useAreaSummary();
  const { reps } = useRepLeaderboard();

  if (loading) return <p className="stores-muted">Loading store analytics…</p>;
  if (error) return <p className="stores-error">{error}</p>;

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Store comparison</h1>
          <p className="page__subtitle">The Sleep Company — territory benchmark</p>
        </div>
      </div>

      {summary && (
        <div className="store-stats">
          <div className="store-stat">
            <div className="store-stat__val">{summary.visits}</div>
            <div className="store-stat__lbl">Visits ({summary.stores} stores)</div>
          </div>
          <div className="store-stat">
            <div className="store-stat__val">{summary.qualified_pct}%</div>
            <div className="store-stat__lbl">Qualified</div>
          </div>
          <div className="store-stat">
            <div className="store-stat__val">{summary.avg_score}</div>
            <div className="store-stat__lbl">Avg score</div>
          </div>
          <div className="store-stat">
            <div className="store-stat__val">
              {summary.top_store ? summary.top_store.store_name : "—"}
            </div>
            <div className="store-stat__lbl">Top store</div>
          </div>
          <div className="store-stat">
            <div className="store-stat__val">
              {summary.needs_attention ? summary.needs_attention.store_name : "—"}
            </div>
            <div className="store-stat__lbl">Needs attention</div>
          </div>
        </div>
      )}

      <div className="stores-table-wrap">
        <table className="stores-table">
          <thead>
            <tr>
              <th>Store</th>
              <th>Visits</th>
              <th>Qualified %</th>
              <th>Ortho demand %</th>
              <th>Competitor mentions</th>
              <th>Trial / EMI</th>
              <th>Top objection</th>
            </tr>
          </thead>
          <tbody>
            {stores.map((s) => (
              <tr key={s.store_id}>
                <td>
                  <Link to={`/manager/stores/${s.store_id}`} className="stores-link">
                    {s.store_name}
                  </Link>
                </td>
                <td>{s.visits}</td>
                <td>{s.qualified_pct}%</td>
                <td>{s.orthopaedic_demand_pct}%</td>
                <td>{s.competitor_mentions}</td>
                <td>
                  {s.trial_requests} / {s.emi_requests}
                </td>
                <td>{s.top_objection || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="stores-section-title">Rep leaderboard</h2>
      {reps.length === 0 ? (
        <p className="stores-muted">No rep activity in this scope yet.</p>
      ) : (
        <div className="stores-table-wrap">
          <table className="stores-table">
            <thead>
              <tr>
                <th>Rep</th>
                <th>Visits</th>
                <th>Avg score</th>
                <th>Win rate</th>
                <th>At risk</th>
                <th>Top objection</th>
              </tr>
            </thead>
            <tbody>
              {reps.map((r) => (
                <tr key={r.agent_id}>
                  <td>{r.name}</td>
                  <td>{r.visits}</td>
                  <td>{r.avg_score}</td>
                  <td>{r.win_rate}%</td>
                  <td>{r.at_risk}</td>
                  <td>{r.top_objection || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

import { Link } from "react-router-dom";
import { useLiveSessions } from "../../data/useLiveSessions";
import { maskPhone } from "../../data/useStoreAnalytics";
import "../stores/stores.css";

export function LiveFloorPage() {
  const { sessions, error } = useLiveSessions();

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Live floor</h1>
          <p className="page__subtitle">Active visits across your stores right now</p>
        </div>
      </div>

      {error && <p className="stores-error">{error}</p>}

      <div className="live-grid">
        {sessions.length === 0 ? (
          <p className="stores-muted">No active visits. Reps start from the mobile app.</p>
        ) : (
          sessions.map((s) => (
            <article key={s.session_id} className="live-card">
              <div className="live-card__top">
                <span className={`live-badge live-badge--${s.status}`}>{s.status}</span>
                <span className="live-card__store">{s.store_name || s.store_id}</span>
              </div>
              <h3 className="live-card__name">{s.customer_name || "Identifying…"}</h3>
              <p className="live-card__phone">WhatsApp {maskPhone(s.customer_phone)}</p>
              <p className="live-card__meta">Rep {s.agent_id}</p>
              <p className="live-card__meta">Started {new Date(s.started_at).toLocaleTimeString()}</p>
            </article>
          ))
        )}
      </div>

      <p className="stores-muted" style={{ marginTop: "1.5rem" }}>
        <Link to="/manager/stores">Compare store performance →</Link>
      </p>
    </div>
  );
}

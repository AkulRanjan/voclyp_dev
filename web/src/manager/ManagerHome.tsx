import { Link } from "react-router-dom";
import { usePitches } from "../data/usePitches";
import { scoreBand } from "../lib/bands";
import "./home.css";

// A compact landing summary for the manager interface, built from the same
// pitch data the list uses.
export function ManagerHome() {
  const { rows } = usePitches();

  const totalPitches = rows.reduce((n, r) => n + r.pitchesTotal, 0);
  const qualified = rows.reduce((n, r) => n + r.pitchesQualified, 0);
  const sales = rows.filter((r) => r.sale).length;
  const avgBest = rows.length
    ? Math.round(rows.reduce((n, r) => n + r.best, 0) / rows.length)
    : 0;

  const stats = [
    { label: "Pitch records", value: rows.length },
    { label: "Total pitches", value: totalPitches },
    { label: "Qualified", value: qualified },
    { label: "Sales made", value: sales },
    { label: "Avg best score", value: avgBest, band: scoreBand(avgBest) },
  ];

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Home</h1>
          <p className="page__subtitle">VoClyp manager console</p>
        </div>
      </div>

      <div className="home-stats">
        {stats.map((s) => (
          <div className="home-stat" key={s.label}>
            <div
              className="home-stat__value"
              style={s.band ? { color: `var(--${s.band.tone}-fg)` } : undefined}
            >
              {s.value}
            </div>
            <div className="home-stat__label">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="home-cta">
        <p>
          Watch live visits on the floor or compare store performance across your territory.
        </p>
        <Link to="/manager/live" className="home-cta__link">
          Live floor →
        </Link>
        <Link to="/manager/stores" className="home-cta__link" style={{ marginLeft: "1rem" }}>
          Store comparison →
        </Link>
      </div>
    </div>
  );
}

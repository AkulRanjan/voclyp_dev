import { useState } from "react";
import { Button } from "../components/Button";
import { getApiKey, setApiKey } from "../data/api";
import { getDataSource, setDataSource, type DataSource } from "../data/source";
import "./settings.css";

// Connection settings: the gateway API key (browser-local) and the data source
// (seed data vs live VoClyp insights).
export function SettingsPage() {
  const [key, setKey] = useState(getApiKey());
  const [source, setSource] = useState<DataSource>(getDataSource());
  const [saved, setSaved] = useState(false);

  function save() {
    setApiKey(key);
    setDataSource(source);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  }

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Settings</h1>
          <p className="page__subtitle">Connection to the VoClyp gateway</p>
        </div>
      </div>

      <div className="settings-card">
        <label className="settings-field">
          <span className="settings-label">Data source</span>
          <div className="settings-toggle">
            <button
              className={`settings-toggle__opt${source === "seed" ? " is-on" : ""}`}
              onClick={() => setSource("seed")}
            >
              Seed data
            </button>
            <button
              className={`settings-toggle__opt${source === "live" ? " is-on" : ""}`}
              onClick={() => setSource("live")}
            >
              Live VoClyp
            </button>
          </div>
          <span className="settings-hint">
            Seed shows the sample pitches. Live reads real insights from the
            gateway (<code>/v1/insights</code>) — requires an API key below.
          </span>
        </label>

        <label className="settings-field">
          <span className="settings-label">Gateway API key</span>
          <input
            type="password"
            className="settings-input"
            placeholder="vclp_..."
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <span className="settings-hint">
            Stored only in this browser. Issued by the VoClyp demo app at
            startup.
          </span>
        </label>

        <div className="settings-actions">
          <Button variant="primary" onClick={save}>
            Save
          </Button>
          {saved && <span className="settings-saved">✓ saved</span>}
        </div>
      </div>
    </div>
  );
}

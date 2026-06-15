import { useState } from "react";
import { Button } from "../components/Button";
import { useAuth } from "../auth/AuthContext";
import { createInvite, type Role } from "../data/auth";
import { getDataSource, setDataSource, type DataSource } from "../data/source";
import "./settings.css";

// Connection + team settings. Console users authenticate with their session
// token, which authorizes /v1 — there is no API key to paste anymore.
export function SettingsPage() {
  const { user } = useAuth();
  const [source, setSource] = useState<DataSource>(getDataSource());
  const [saved, setSaved] = useState(false);

  function save() {
    setDataSource(source);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  }

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Settings</h1>
          <p className="page__subtitle">Signed in as {user?.email}</p>
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
            gateway using your session — no API key needed; the server enforces
            your role.
          </span>
        </label>

        <div className="settings-actions">
          <Button variant="primary" onClick={save}>
            Save
          </Button>
          {saved && <span className="settings-saved">✓ saved</span>}
        </div>
      </div>

      {user?.role === "manager" && <InvitePanel />}
    </div>
  );
}

// Managers mint single-use invites so teammates can join this tenant. The role
// is fixed by the invite, so nobody can self-elect to manager.
function InvitePanel() {
  const [role, setRole] = useState<Role>("sales");
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  async function generate() {
    setError(null);
    setBusy(true);
    try {
      const code = await createInvite(role);
      const url = `${window.location.origin}/signup?role=${role}&invite=${encodeURIComponent(code)}`;
      setLink(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!link) return;
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="settings-card">
      <div className="settings-field">
        <span className="settings-label">Invite a teammate</span>
        <div className="settings-toggle">
          <button className={`settings-toggle__opt${role === "sales" ? " is-on" : ""}`} onClick={() => setRole("sales")}>
            Sales hero
          </button>
          <button className={`settings-toggle__opt${role === "manager" ? " is-on" : ""}`} onClick={() => setRole("manager")}>
            Manager
          </button>
        </div>
        <span className="settings-hint">
          Single-use link that lets one person join your organization as a{" "}
          {role === "manager" ? "manager" : "sales hero"}.
        </span>
      </div>

      <div className="settings-actions">
        <Button variant="primary" onClick={generate} disabled={busy}>
          {busy ? "Generating…" : "Generate invite link"}
        </Button>
      </div>

      {error && <div className="settings-invite-err">{error}</div>}
      {link && (
        <div className="settings-invite">
          <input readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
          <Button variant="outline" onClick={copy}>{copied ? "Copied" : "Copy"}</Button>
        </div>
      )}
    </div>
  );
}

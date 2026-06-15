import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import { useAuth } from "./AuthContext";
import { homeFor, parseRole, roleLabel } from "../data/auth";
import "./auth.css";

// Step 2 (new account): the role was chosen on the welcome screen and arrives
// as ?role=; here we only collect the credentials and profile.
export function SignupPage() {
  const { user, loading, signup } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const role = parseRole(params.get("role"));
  const invitedOrg = params.get("org") || "";
  const invite = params.get("invite") || "";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [org, setOrg] = useState(invitedOrg);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to={homeFor(user.role)} replace />;
  if (!role) return <Navigate to="/welcome" replace />;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    if (password !== confirm) return setError("Passwords do not match.");
    setBusy(true);
    try {
      const u = await signup({
        name, email, password, role: role!, org: org || undefined,
        invite: invite || undefined,
      });
      navigate(homeFor(u.role), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-brand">
          <span className="auth-logo">V</span>
          <span className="auth-brandname">VoClyp</span>
        </div>

        <Link to="/welcome" className="auth-context">
          <Icon name="chevron-left" size={14} />
          {roleLabel(role)}
          <span className="auth-context__change">change</span>
        </Link>

        <h1 className="auth-title">Create your account</h1>
        <p className="auth-sub">Set up your {roleLabel(role)} login</p>

        <label className="auth-field">
          <span>Full name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </label>
        <label className="auth-field">
          <span>Email</span>
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="auth-field">
          <span>
            Organization{" "}
            <span className="auth-opt">{invite ? "(from your invite)" : "(optional)"}</span>
          </span>
          <input
            value={org}
            onChange={(e) => setOrg(e.target.value)}
            placeholder="VoClyp Demo"
            readOnly={!!invite}
          />
        </label>
        <div className="auth-row">
          <label className="auth-field">
            <span>Password</span>
            <input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          <label className="auth-field">
            <span>Confirm</span>
            <input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
          </label>
        </div>

        {error && <div className="auth-error">{error}</div>}

        <button className="auth-submit" type="submit" disabled={busy}>
          {busy ? "Creating…" : `Create ${role === "manager" ? "manager" : "sales"} account`}
        </button>

        <p className="auth-alt">
          Already have an account? <Link to={`/login?role=${role}`}>Sign in</Link>
        </p>
      </form>
    </div>
  );
}

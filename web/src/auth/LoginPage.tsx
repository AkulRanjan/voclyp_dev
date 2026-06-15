import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import { useAuth } from "./AuthContext";
import { homeFor, parseRole, roleLabel } from "../data/auth";
import "./auth.css";

// Step 2: credentials. The role chosen on the welcome screen arrives as ?role=
// and is shown for context; on success we route by the account's actual
// (server-returned) role.
export function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const role = parseRole(params.get("role"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to={homeFor(user.role)} replace />;
  // Enforce the role-first flow: no role chosen yet -> back to the chooser.
  if (!role) return <Navigate to="/welcome" replace />;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const u = await login(email, password);
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

        <h1 className="auth-title">Sign in</h1>
        <p className="auth-sub">Enter your email and password</p>

        <label className="auth-field">
          <span>Email</span>
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </label>
        <label className="auth-field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && <div className="auth-error">{error}</div>}

        <button className="auth-submit" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <p className="auth-alt">
          New here? <Link to={`/signup?role=${role}`}>Create an account</Link>
        </p>
      </form>
    </div>
  );
}

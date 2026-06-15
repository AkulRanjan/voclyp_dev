import { Navigate, useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { useAuth } from "./AuthContext";
import { homeFor, type Role } from "../data/auth";
import "./auth.css";

// Step 1 of sign-in: choose your role. The choice is carried into the
// credentials screen (and into signup, where it becomes the account's role).
export function WelcomePage() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  if (!loading && user) return <Navigate to={homeFor(user.role)} replace />;

  function pick(role: Role) {
    navigate(`/login?role=${role}`);
  }

  return (
    <div className="auth-shell">
      <div className="auth-card auth-card--wide">
        <div className="auth-brand">
          <span className="auth-logo">V</span>
          <span className="auth-brandname">VoClyp</span>
        </div>
        <h1 className="auth-title">Welcome</h1>
        <p className="auth-sub">How will you use VoClyp?</p>

        <div className="welcome-roles">
          <button type="button" className="welcome-role" onClick={() => pick("manager")}>
            <span className="welcome-role__icon"><Icon name="bar-chart" size={22} /></span>
            <span className="welcome-role__title">Manager</span>
            <span className="welcome-role__desc">
              Review pitches, signals &amp; coaching across the team
            </span>
            <span className="welcome-role__go">Continue <Icon name="chevron-right" size={15} /></span>
          </button>

          <button type="button" className="welcome-role" onClick={() => pick("sales")}>
            <span className="welcome-role__icon"><Icon name="mic" size={22} /></span>
            <span className="welcome-role__title">Sales hero</span>
            <span className="welcome-role__desc">
              Record field visits and turn them into insights
            </span>
            <span className="welcome-role__go">Continue <Icon name="chevron-right" size={15} /></span>
          </button>
        </div>
      </div>
    </div>
  );
}

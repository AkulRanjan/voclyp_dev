import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { homeFor, type Role } from "../data/auth";

function Loading() {
  return <div className="auth-loading">Loading…</div>;
}

// Must be signed in; otherwise start the role-first flow at /welcome.
export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/welcome" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

// Must hold a specific role; a mismatched role is sent to its own home. This is
// the isolation boundary — a sales user cannot render manager screens and vice
// versa, and the role is the server-signed claim (not editable client-side).
export function RequireRole({ role }: { role: Role }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={homeFor(user.role)} replace />;
  return <Outlet />;
}

// Root and unknown paths: send to the right place based on auth/role.
export function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return <Navigate to={user ? homeFor(user.role) : "/welcome"} replace />;
}

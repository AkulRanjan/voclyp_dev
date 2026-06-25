import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { homeFor, isManagerRole, type Role } from "../data/auth";

function Loading() {
  return <div className="auth-loading">Loading…</div>;
}

export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/welcome" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

export function RequireRole({ role }: { role: Role }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={homeFor(user.role)} replace />;
  return <Outlet />;
}

export function RequireManager() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (!isManagerRole(user.role)) return <Navigate to={homeFor(user.role)} replace />;
  return <Outlet />;
}

export function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return <Navigate to={user ? homeFor(user.role) : "/welcome"} replace />;
}

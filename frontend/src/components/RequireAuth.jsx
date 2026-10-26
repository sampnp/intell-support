import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { Spinner } from "./ui";

/**
 * Route guard. Logged out -> /login (remembering where you were going); wrong role -> home.
 * The API enforces the same rules; this only keeps the UI from showing pages that would 403.
 */
export default function RequireAuth({ role, children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner label="Checking your session…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (role && user.role !== role) return <Navigate to="/" replace />;
  return children ?? <Outlet />;
}

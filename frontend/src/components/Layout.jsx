import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

function NavItem({ to, children }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 text-sm font-medium ${
          isActive ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:text-slate-900"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function Layout() {
  const { user, isAgent, logout } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3">
          <span className="mr-4 text-lg font-semibold text-indigo-700">Intell-Support</span>
          <nav className="flex flex-1 flex-wrap gap-1">
            {isAgent && <NavItem to="/dashboard">Dashboard</NavItem>}
            <NavItem to="/tickets">Tickets</NavItem>
            <NavItem to="/tickets/new">New ticket</NavItem>
            <NavItem to="/kb">Knowledge base</NavItem>
          </nav>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-600">
              {user.full_name}{" "}
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-500">
                {user.role}
              </span>
            </span>
            <button type="button" className="btn-secondary" onClick={logout}>
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { useAuth } from "../auth/AuthContext";
import { roleLabel } from "../data/auth";
import type { NavItem } from "./nav";
import "./sidebar.css";

// Fixed-width sidebar matching the reference shell: brand mark + collapse
// chevron, vertical nav with icon + label (active item gets a teal pill),
// footer with the signed-in user and Logout. There is no cross-interface
// switch — the two roles are isolated, so neither can navigate into the other.
export function Sidebar({ nav, interfaceLabel }: { nav: NavItem[]; interfaceLabel: string }) {
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function onLogout() {
    await logout();
    navigate("/welcome", { replace: true });
  }

  const initial = (user?.name || "?").trim().charAt(0).toUpperCase();

  return (
    <aside className={`sidebar${collapsed ? " sidebar--collapsed" : ""}`}>
      <div className="sidebar__brand">
        <span className="sidebar__logo">V</span>
        {!collapsed && (
          <span className="sidebar__brandtext">
            VoClyp
            <span className="sidebar__brandsub">{interfaceLabel}</span>
          </span>
        )}
        <button
          className="sidebar__collapse"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <Icon name={collapsed ? "chevron-right" : "chevron-left"} size={16} />
        </button>
      </div>

      <nav className="sidebar__nav">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `sidebar__item${isActive ? " sidebar__item--active" : ""}`
            }
            title={item.label}
          >
            <Icon name={item.icon} size={18} className="sidebar__icon" />
            {!collapsed && <span className="sidebar__label">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar__footer">
        <div className="sidebar__user">
          <span className="sidebar__avatar">{initial}</span>
          {!collapsed && (
            <span className="sidebar__usermeta">
              <span className="sidebar__username">{user?.name}</span>
              <span className="sidebar__userrole">{user ? roleLabel(user.role) : ""}</span>
            </span>
          )}
        </div>

        <button className="sidebar__item sidebar__logout" onClick={onLogout} title="Logout">
          <Icon name="log-out" size={18} className="sidebar__icon" />
          {!collapsed && <span className="sidebar__label">Logout</span>}
        </button>
      </div>
    </aside>
  );
}

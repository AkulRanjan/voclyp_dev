import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import type { NavItem } from "./nav";
import "./sidebar.css";

// Fixed-width sidebar matching the reference shell: brand mark + collapse
// chevron, vertical nav with icon + label (active item gets a teal pill),
// footer with the current user, an interface switch, and Logout.
export function Sidebar({
  nav,
  interfaceLabel,
  switchTo,
  switchLabel,
}: {
  nav: NavItem[];
  interfaceLabel: string;
  switchTo: string;
  switchLabel: string;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();

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
        <button
          className="sidebar__switch"
          onClick={() => navigate(switchTo)}
          title={switchLabel}
        >
          <Icon name="refresh" size={16} className="sidebar__icon" />
          {!collapsed && <span className="sidebar__label">{switchLabel}</span>}
        </button>

        <div className="sidebar__user">
          <span className="sidebar__avatar">S</span>
          {!collapsed && <span className="sidebar__label">Siddharth</span>}
        </div>

        <button className="sidebar__item sidebar__logout" title="Logout">
          <Icon name="log-out" size={18} className="sidebar__icon" />
          {!collapsed && <span className="sidebar__label">Logout</span>}
        </button>
      </div>
    </aside>
  );
}

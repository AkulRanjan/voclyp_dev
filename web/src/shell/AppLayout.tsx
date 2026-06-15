import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { MANAGER_NAV, FIELD_NAV } from "./nav";
import "./layout.css";

export function ManagerLayout() {
  return (
    <div className="app">
      <Sidebar nav={MANAGER_NAV} interfaceLabel="Manager" />
      <main className="app__main">
        <Outlet />
      </main>
    </div>
  );
}

export function FieldLayout() {
  return (
    <div className="app">
      <Sidebar nav={FIELD_NAV} interfaceLabel="Salesperson" />
      <main className="app__main">
        <Outlet />
      </main>
    </div>
  );
}

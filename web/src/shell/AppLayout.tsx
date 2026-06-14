import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { MANAGER_NAV, FIELD_NAV } from "./nav";
import "./layout.css";

export function ManagerLayout() {
  return (
    <div className="app">
      <Sidebar
        nav={MANAGER_NAV}
        interfaceLabel="Manager"
        switchTo="/field"
        switchLabel="Switch to Salesperson"
      />
      <main className="app__main">
        <Outlet />
      </main>
    </div>
  );
}

export function FieldLayout() {
  return (
    <div className="app">
      <Sidebar
        nav={FIELD_NAV}
        interfaceLabel="Salesperson"
        switchTo="/manager/pitches"
        switchLabel="Switch to Manager"
      />
      <main className="app__main">
        <Outlet />
      </main>
    </div>
  );
}

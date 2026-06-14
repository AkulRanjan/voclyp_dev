import type { IconName } from "../components/Icon";

export interface NavItem {
  label: string;
  to: string;
  icon: IconName;
  end?: boolean; // exact-match active (for index routes)
}

// Manager interface — the analytics/coaching surface. Pitches is the section
// built out here; the rest are real destinations in the shell with stub pages.
export const MANAGER_NAV: NavItem[] = [
  { label: "Home", to: "/manager", icon: "home", end: true },
  { label: "Pitches", to: "/manager/pitches", icon: "target" },
  { label: "Conversations", to: "/manager/conversations", icon: "file-text" },
  { label: "Retailers", to: "/manager/retailers", icon: "store" },
  { label: "Workers", to: "/manager/workers", icon: "users" },
  { label: "Scripts", to: "/manager/scripts", icon: "list" },
  { label: "Campaigns", to: "/manager/campaigns", icon: "megaphone" },
  { label: "Mission Metrics", to: "/manager/metrics", icon: "bar-chart" },
  { label: "Settings", to: "/manager/settings", icon: "settings" },
];

// Salesperson interface — the field-capture surface.
export const FIELD_NAV: NavItem[] = [
  { label: "Record a visit", to: "/field", icon: "mic", end: true },
  { label: "My pitches", to: "/field/pitches", icon: "target" },
  { label: "Settings", to: "/field/settings", icon: "settings" },
];

import type { IconName } from "../components/Icon";

export interface NavItem {
  label: string;
  to: string;
  icon: IconName;
  end?: boolean;
}

export const MANAGER_NAV: NavItem[] = [
  { label: "Live floor", to: "/manager/live", icon: "mic", end: true },
  { label: "Stores", to: "/manager/stores", icon: "store" },
  { label: "Pitches", to: "/manager/pitches", icon: "target" },
  { label: "Home", to: "/manager", icon: "home" },
  { label: "Settings", to: "/manager/settings", icon: "settings" },
];

export const FIELD_NAV: NavItem[] = [
  { label: "Record a visit", to: "/field", icon: "mic", end: true },
  { label: "My pitches", to: "/field/pitches", icon: "target" },
  { label: "Settings", to: "/field/settings", icon: "settings" },
];

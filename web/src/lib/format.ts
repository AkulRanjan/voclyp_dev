// Small formatting helpers, centralized so the list and drawer agree.

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** 87 -> "1:27" */
export function secondsToClock(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${String(rem).padStart(2, "0")}`;
}

/** ISO date -> "12 Jun 26" */
export function formatShortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const day = d.getDate();
  const month = MONTHS[d.getMonth()];
  const year = String(d.getFullYear()).slice(-2);
  return `${day} ${month} ${year}`;
}

/** 300.5 -> "300.5s" (one decimal, trailing .0 trimmed) */
export function formatTimestamp(seconds: number): string {
  const rounded = Math.round(seconds * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)}s`;
}

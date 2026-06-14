import type { Tone } from "../lib/bands";
import "./badge.css";

// Small status badge (used for the Intent column). Tone-driven, soft tinted.
export function Badge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

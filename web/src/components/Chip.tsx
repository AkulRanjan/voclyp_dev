import type { ChipTone } from "../lib/chips";
import "./chip.css";

// Soft tinted pill. Used for Signals/Coaching tags. `block` lets a long
// sentence-style chip wrap to 1-2 lines instead of staying inline.
export function Chip({
  tone,
  children,
  block = false,
}: {
  tone: ChipTone;
  children: React.ReactNode;
  block?: boolean;
}) {
  return (
    <span className={`chip chip--${tone}${block ? " chip--block" : ""}`}>
      {children}
    </span>
  );
}

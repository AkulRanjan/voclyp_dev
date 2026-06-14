// Chip tone mapping for Signals and Coaching groups, centralized so the two
// sections stay visually consistent. Tones map to soft tinted styles in
// chip.css (light background + saturated text/border, never solid).

export type ChipTone =
  | "blue"
  | "green"
  | "pink"
  | "amber"
  | "red"
  | "purple"
  | "gray";

export type SignalGroup =
  | "products"
  | "positive"
  | "negative"
  | "objections"
  | "explicitConcerns"
  | "implicitConcerns";

export type CoachingGroup = "missed";

export const SIGNAL_GROUPS: {
  key: SignalGroup;
  label: string;
  tone: ChipTone;
}[] = [
  { key: "products", label: "Products", tone: "blue" },
  { key: "positive", label: "Positive", tone: "green" },
  { key: "negative", label: "Negative", tone: "pink" },
  { key: "objections", label: "Objections", tone: "amber" },
  { key: "explicitConcerns", label: "Explicit Concerns", tone: "red" },
  { key: "implicitConcerns", label: "Implicit Concerns", tone: "amber" },
];

export const COACHING_GROUPS: {
  key: CoachingGroup;
  label: string;
  tone: ChipTone;
}[] = [{ key: "missed", label: "Missed", tone: "purple" }];

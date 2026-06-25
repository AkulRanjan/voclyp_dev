import { CheckCircle2, MapPin, Mic, Trash2 } from "lucide-react";

export function CaptureVisual() {
  return (
    <div className="rounded-2xl border border-border bg-background p-5">
      <div className="mb-3 flex gap-1.5" aria-hidden>
        <span className="h-2 w-2 rounded-full bg-border" />
        <span className="h-2 w-2 rounded-full bg-border" />
        <span className="h-2 w-2 rounded-full bg-border" />
      </div>
      <div className="rounded-xl border border-border p-5">
        <p className="text-caption text-muted-foreground">Customer name</p>
        <div className="text-body-sm mt-1 rounded-lg border border-border px-3 py-2 text-muted-foreground">
          Priya S.
        </div>
        <p className="text-caption mt-3 text-center text-muted-foreground">
          Recorded for quality. Auto-deleted after the visit.
        </p>
        <div className="mt-3 flex gap-2">
          <span className="btn-primary flex-1 rounded-lg py-2 text-center text-caption">
            Allow recording
          </span>
          <span className="flex-1 rounded-lg border border-border py-2 text-center text-caption text-muted-foreground">
            Not now
          </span>
        </div>
      </div>
      <div className="text-caption mt-3 flex justify-center gap-2 font-medium text-muted-foreground">
        <span className="rounded-full border border-border px-2 py-0.5">offline</span>
        <span className="rounded-full border border-border px-2 py-0.5">syncing</span>
        <span className="rounded-full border border-amber/40 bg-amber/10 px-2 py-0.5 text-amber">
          synced
        </span>
      </div>
    </div>
  );
}

export function ConsentVisual() {
  const steps = [
    { icon: Mic, label: "Conversation recorded" },
    { icon: MapPin, label: "Processed and stored in India" },
    { icon: Trash2, label: "Audio auto-deleted within hours" },
    { icon: CheckCircle2, label: "Insights ready" },
  ];
  return (
    <div className="space-y-2">
      {steps.map((s) => (
        <div
          key={s.label}
          className="flex items-center gap-3 rounded-xl border border-border bg-background px-4 py-3"
        >
          <div className="icon-tile !h-8 !w-8 shrink-0">
            <s.icon size={15} strokeWidth={1.75} />
          </div>
          <span className="text-body-sm font-medium">{s.label}</span>
        </div>
      ))}
    </div>
  );
}

export function CoachVisual() {
  const themes = [
    { label: "Price too high", pct: 72 },
    { label: "Asked for EMI / financing", pct: 58 },
    { label: "Compared to competitor", pct: 41 },
  ];
  return (
    <div className="space-y-2 rounded-2xl border border-border bg-background p-5">
      <p className="eyebrow mb-1">Top customer objections · this month</p>
      {themes.map((t) => (
        <div
          key={t.label}
          className="text-body-sm flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5"
        >
          <span className="text-muted-foreground">{t.label}</span>
          <div className="h-1 w-16 shrink-0 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-foreground/25"
              style={{ width: `${t.pct}%` }}
            />
          </div>
        </div>
      ))}
      <div className="text-body-sm rounded-lg border border-amber/30 bg-amber/5 px-3 py-2.5">
        <span className="font-semibold text-amber">Signal →</span> Price
        objections up 18% in the South region.
      </div>
    </div>
  );
}

export function AccountabilityVisual() {
  const cols = [
    { title: "Demand", items: ["Smaller SKUs", "Bundled service", "Local language"] },
    { title: "Competitor", items: ["Brand X pricing", "Faster delivery"] },
    { title: "Action", items: ["Marketing brief", "Product backlog →"] },
  ];
  return (
    <div className="grid grid-cols-3 gap-2">
      {cols.map((c) => (
        <div key={c.title}>
          <p className="eyebrow mb-2">{c.title}</p>
          {c.items.map((item) => (
            <div
              key={item}
              className="text-caption mb-1.5 rounded-lg border border-border bg-background px-2 py-1.5 text-muted-foreground"
            >
              {item}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

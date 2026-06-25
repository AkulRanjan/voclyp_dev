import { Eye, ShieldCheck, Trash2 } from "lucide-react";
import { SectionReveal } from "./FadeIn";
import { SectionHeader } from "./SectionHeader";

const PILLARS = [
  {
    icon: ShieldCheck,
    title: "Permission, not surveillance",
    body: "A short form notes the customer's name and that the visit is recorded for quality. They can always say no.",
  },
  {
    icon: Trash2,
    title: "Audio that doesn't linger",
    body: "Recordings are deleted once processed, and never kept beyond a couple of hours of the visit.",
  },
  {
    icon: Eye,
    title: "Delete on demand",
    body: "A single button wipes a recording on the spot, so a customer always has that assurance.",
  },
];

export function Privacy() {
  return (
    <SectionReveal>
      <section id="privacy" className="border-t border-border bg-muted/50">
        <div className="section-shell px-5 sm:px-6 md:px-8 lg:px-12 text-center">
          <SectionHeader
            eyebrow="Privacy & trust"
            title="Built for enterprises who"
            highlight="can't afford a privacy slip."
          />

          <div className="grid gap-5 sm:grid-cols-3">
            {PILLARS.map(({ icon: Icon, title, body }) => (
              <div
                key={title}
                className="rounded-xl border border-border bg-background p-6 text-left"
              >
                <span className="icon-tile">
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                <h3 className="text-card-title mt-4">{title}</h3>
                <p className="mt-2 text-base leading-relaxed text-foreground/70">
                  {body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </SectionReveal>
  );
}

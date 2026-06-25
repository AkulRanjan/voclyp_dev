import { SectionReveal } from "./FadeIn";
import { SectionHeader } from "./SectionHeader";
import { Button } from "./ui/button";

const TIERS = [
  {
    name: "Team",
    tagline: "For a single field team getting started.",
    popular: true,
    features: [
      "Unlimited field recordings",
      "Privacy controls and India storage",
      "Transcription in 120+ languages",
      "Market-intelligence dashboard",
      "Objection and demand-signal tracking",
      "Email support",
    ],
  },
  {
    name: "Enterprise",
    tagline: "For multi-region field forces at scale.",
    popular: false,
    features: [
      "Everything in Team",
      "Multi-region rollout and benchmarking",
      "CRM and BI integrations (API)",
      "SSO and role-based access",
      "Compliance and audit exports",
      "Dedicated success manager",
    ],
  },
];

export function Pricing({ showHeader = true }: { showHeader?: boolean }) {
  return (
    <SectionReveal>
      <section id="pricing" className="section-shell">
        {showHeader && (
          <SectionHeader
            eyebrow="Pricing"
            title="Priced around your field force,"
            highlight="not your headaches."
          />
        )}

        <div className="mx-auto grid max-w-4xl gap-5 md:grid-cols-2">
          {TIERS.map((t) => (
            <div
              key={t.name}
              className={`relative flex h-full flex-col rounded-xl border p-7 ${
                t.popular ? "border-foreground/12 bg-muted/50" : "border-border bg-background"
              }`}
            >
              {t.popular && (
                <span className="text-caption absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-amber px-3 py-0.5 font-semibold uppercase tracking-wide text-[#1a1205]">
                  Most popular
                </span>
              )}
              <h3 className="text-card-title">{t.name}</h3>
              <p className="text-body-sm mt-2 min-h-[2.5rem] text-muted-foreground">
                {t.tagline}
              </p>
              <ul className="my-6 flex flex-1 flex-col gap-2">
                {t.features.map((f) => (
                  <li key={f} className="text-body-sm text-muted-foreground">
                    {f}
                  </li>
                ))}
              </ul>
              <Button
                href="/#book"
                variant={t.popular ? "primary" : "secondary"}
                className="w-full"
              >
                {t.popular ? "Book a demo" : "Talk to sales"}
              </Button>
            </div>
          ))}
        </div>

        <p className="text-caption mx-auto mt-8 max-w-xl text-center text-muted-foreground">
          We price around your team size and scope the rollout with you, including
          the devices your agents use in the field. Book a demo for a tailored
          quote.
        </p>
      </section>
    </SectionReveal>
  );
}

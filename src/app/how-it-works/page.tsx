import type { Metadata } from "next";
import {
  BarChart3,
  Globe2,
  ShieldCheck,
  Smartphone,
  Target,
  Trash2,
} from "lucide-react";
import { HowItWorks } from "@/components/HowItWorks";
import { PageBreadcrumb } from "@/components/PageBreadcrumb";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "How it works — VoClyp",
  description:
    "A field conversation becomes a customer recommendation report, an agent playbook, and market intelligence for your teams, in minutes. Privacy-first, audio auto-deleted.",
};

const OUTPUTS = [
  {
    icon: Smartphone,
    audience: "For the customer",
    title: "A personalized recommendation report",
    body: "Minutes after the visit, the customer gets a clear shortlist of products matched to what they actually asked for, sent on WhatsApp or SMS.",
    points: ["Matched to stated needs", "Pricing and EMI options", "Sent within minutes"],
  },
  {
    icon: Target,
    audience: "For the agent",
    title: "A next-best-action playbook",
    body: "After the visit, the agent receives a playbook on how to close: which objections to handle, what to offer, and when to follow up.",
    points: ["Objection counters", "Offers to lead with", "Follow-up reminders"],
  },
  {
    icon: BarChart3,
    audience: "For your teams",
    title: "Aggregated market intelligence",
    body: "Every conversation rolls up into demand signals, competitor mentions, and pricing trends, routed to marketing and product automatically.",
    points: ["Demand and objection trends", "Competitor mentions", "Weekly territory reports"],
  },
];

const TRUST = [
  { icon: ShieldCheck, label: "Permission-first capture" },
  { icon: Trash2, label: "Audio auto-deleted within hours" },
  { icon: Globe2, label: "120+ Indian languages, stored in India" },
];

export default function HowItWorksPage() {
  return (
    <main className="pt-32">
      <PageBreadcrumb current="How it works" />
      <section className="site-container">
        <div className="mx-auto max-w-3xl text-center">
          <span className="eyebrow">How it works</span>
          <h1 className="text-display mt-4 text-balance">
            One conversation in,{" "}
            <span className="bg-gradient-to-r from-indigo via-indigo/70 to-amber bg-clip-text text-transparent">
              intelligence out.
            </span>
          </h1>
          <p className="text-lead mx-auto mt-6 max-w-2xl text-muted-foreground">
            VoClyp captures the full visit, then analyzes it once the conversation
            ends. Reports land for the customer, agent, and your teams within
            minutes.
          </p>
        </div>
      </section>

      <HowItWorks showHeader={false} />

      <section className="section-shell border-t border-border bg-muted/40">
        <div className="mx-auto max-w-5xl">
          <div className="mx-auto mb-12 max-w-2xl text-center">
            <span className="eyebrow">What everyone walks away with</span>
            <h2 className="text-title mt-3">
              One visit. <span className="text-bold-point">Three deliverables.</span>
            </h2>
          </div>

          <div className="grid gap-5 md:grid-cols-3">
            {OUTPUTS.map(({ icon: Icon, audience, title, body, points }) => (
              <div
                key={audience}
                className="flex flex-col rounded-2xl border border-border bg-background p-6"
              >
                <span className="icon-tile">
                  <Icon size={18} strokeWidth={1.75} />
                </span>
                <span className="eyebrow mt-4 text-indigo/70">{audience}</span>
                <h3 className="text-card-title mt-1">{title}</h3>
                <p className="text-body-sm mt-2 text-muted-foreground">{body}</p>
                <ul className="mt-4 space-y-1.5 border-t border-border pt-4">
                  {points.map((p) => (
                    <li key={p} className="text-caption text-muted-foreground">
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section-shell">
        <div className="mx-auto max-w-4xl">
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-border bg-muted/30 px-6 py-6 sm:flex-row sm:justify-center sm:gap-8">
            {TRUST.map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-2.5">
                <Icon size={16} className="text-indigo" />
                <span className="text-body-sm text-foreground/80">{label}</span>
              </div>
            ))}
          </div>

          <div className="mt-12 text-center">
            <h2 className="text-title">
              See it run on{" "}
              <span className="text-bold-point">your own field data.</span>
            </h2>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Button href="/#book" variant="primary">
                Book a 15-min discovery call
              </Button>
              <Button href="/#demo" variant="secondary">
                Watch the live demo
              </Button>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

import type { Metadata } from "next";
import { PageBreadcrumb } from "@/components/PageBreadcrumb";
import { Pricing } from "@/components/Pricing";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Pricing — VoClyp",
  description:
    "VoClyp is priced around your field force and rollout, not seat counts. Start with a free pilot and book a demo for a tailored quote.",
};

const PRICING_FAQ = [
  {
    q: "How is VoClyp priced?",
    a: "We price around the size of your field force and the scope of your rollout, including the devices your agents already use. You get a tailored quote after a short scoping call.",
  },
  {
    q: "Is there a free pilot?",
    a: "Yes. Early partners run a three-week pilot on one team's real visits, so you can evaluate VoClyp on your own data before committing.",
  },
  {
    q: "Do you charge per user or per conversation?",
    a: "Neither rigidly. Plans are scoped to your team and rollout so the cost tracks the value you get, not an arbitrary seat count.",
  },
];

export default function PricingPage() {
  return (
    <main className="pt-32">
      <PageBreadcrumb current="Pricing" />
      <section className="site-container">
        <div className="mx-auto max-w-3xl text-center">
          <span className="eyebrow">Pricing</span>
          <h1 className="text-display mt-4 text-balance">
            Priced around your field force,{" "}
            <span className="bg-gradient-to-r from-indigo via-indigo/70 to-amber bg-clip-text text-transparent">
              not your headaches.
            </span>
          </h1>
          <p className="text-lead mx-auto mt-6 max-w-2xl text-muted-foreground">
            Two plans, scoped to your team and rollout. Start with a free pilot
            and only scale when the insight earns it.
          </p>
        </div>
      </section>

      <Pricing showHeader={false} />

      <section className="section-shell border-t border-border">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-title mb-10 text-center">Pricing questions</h2>
          <div className="divide-y divide-border border-y border-border">
            {PRICING_FAQ.map((item) => (
              <div key={item.q} className="py-5">
                <h3 className="text-card-title">{item.q}</h3>
                <p className="text-body-sm mt-2 text-muted-foreground">
                  {item.a}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-12 text-center">
            <Button href="/#book" variant="primary">
              Book a demo &amp; get a quote
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}

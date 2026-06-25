"use client";

import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";

const ease = [0.22, 1, 0.36, 1] as const;

const STEPS = [
  {
    week: "Week 1",
    title: "Pilot on real visits",
    body: "We set up VoClyp with one of your field teams and start capturing live conversations. No new hardware, no workflow change.",
  },
  {
    week: "Week 2",
    title: "Review the insight together",
    body: "We walk your marketing, product, and sales leads through the dashboard: objections, demand signals, and competitor mentions from your own market.",
  },
  {
    week: "Week 3",
    title: "Decide with your data",
    body: "You judge VoClyp on the intelligence it surfaced for your business, not on our pitch. Continue only if it earns its place.",
  },
];

export function Pilot() {
  return (
    <section className="section-shell border-t border-border">
      <div className="mx-auto max-w-4xl">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "0px 0px -60px 0px" }}
          transition={{ duration: 0.45, ease }}
        >
          <span className="eyebrow">Start with a free pilot</span>
          <h2 className="text-title mt-3">
            See it work on your field data{" "}
            <span className="text-bold-point">before you commit a rupee.</span>
          </h2>
          <p className="text-body-sm mx-auto mt-4 max-w-2xl text-muted-foreground">
            A three-week pilot, scoped to one team, so you can evaluate VoClyp on
            real outcomes with zero risk.
          </p>
        </motion.div>

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {STEPS.map((step, i) => (
            <motion.div
              key={step.week}
              className="relative rounded-2xl border border-border bg-muted/40 p-6"
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "0px 0px -60px 0px" }}
              transition={{ duration: 0.45, delay: i * 0.1, ease }}
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-full border border-indigo/25 bg-indigo/[0.06] text-sm font-semibold text-indigo">
                {i + 1}
              </span>
              <p className="eyebrow mt-4 text-indigo/70">{step.week}</p>
              <h3 className="text-card-title mt-1">{step.title}</h3>
              <p className="text-body-sm mt-2 text-muted-foreground">
                {step.body}
              </p>
            </motion.div>
          ))}
        </div>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Button href="/#book" variant="primary">
            Start a free pilot
          </Button>
          <Button href="/pricing" variant="secondary">
            See pricing
          </Button>
        </div>
      </div>
    </section>
  );
}

"use client";

import {
  Hand,
  LayoutDashboard,
  ShieldCheck,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";
import { SectionHeader } from "./SectionHeader";

const ease = [0.22, 1, 0.36, 1] as const;

const STEPS: {
  icon: LucideIcon;
  title: string;
  body: string;
}[] = [
  {
    icon: ShieldCheck,
    title: "Customer gives permission",
    body: "A quick form notes their name and that the visit is recorded for quality. Decline anytime and the visit carries on.",
  },
  {
    icon: Hand,
    title: "Agent records the visit",
    body: "The whole field conversation is captured on the device the agent already uses, online or off.",
  },
  {
    icon: Waves,
    title: "VoClyp analyzes, then forgets",
    body: "Once the visit ends, audio is transcribed, translated, and mined for signals, then deleted within a couple of hours.",
  },
  {
    icon: LayoutDashboard,
    title: "Your teams get insight",
    body: "Market trends, objections, and demand signals land in dashboards for marketing, product, and sales.",
  },
];

export function HowItWorks({ showHeader = true }: { showHeader?: boolean }) {
  const trackRef = useRef<HTMLOListElement>(null);
  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start 80%", "end 60%"],
  });
  const lineScale = useTransform(scrollYProgress, [0, 1], [0, 1]);

  return (
    <section id="how" className="section-shell">
      {showHeader && (
        <SectionHeader
          eyebrow="How it works"
          title="From field conversation to market insight"
          highlight="in minutes."
        />
      )}

      <ol ref={trackRef} className="relative mx-auto max-w-3xl">
        <span
          className="absolute left-[1.125rem] top-2 bottom-2 w-px bg-border md:left-1/2 md:-translate-x-1/2"
          aria-hidden
        />
        <motion.span
          className="absolute left-[1.125rem] top-2 bottom-2 w-px origin-top bg-gradient-to-b from-indigo to-amber md:left-1/2 md:-translate-x-1/2"
          style={{ scaleY: lineScale }}
          aria-hidden
        />

        {STEPS.map((step, i) => {
          const flip = i % 2 === 1;
          return (
            <motion.li
              key={step.title}
              className={`relative flex items-start gap-5 pb-10 last:pb-0 md:gap-0 ${
                flip ? "md:flex-row-reverse" : ""
              }`}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "0px 0px -80px 0px" }}
              transition={{ duration: 0.5, delay: i * 0.08, ease }}
            >
              <div className="relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border bg-background text-indigo shadow-sm md:absolute md:left-1/2 md:-translate-x-1/2">
                <step.icon size={17} strokeWidth={1.75} />
              </div>

              <div
                className={`flex-1 md:w-1/2 ${
                  flip
                    ? "md:pr-10 md:text-right"
                    : "md:pl-10"
                }`}
              >
                <div className="rounded-xl border border-border bg-muted/40 p-5">
                  <span className="eyebrow text-indigo/70">
                    Step {i + 1}
                  </span>
                  <h3 className="text-card-title mt-1.5">{step.title}</h3>
                  <p className="text-body-sm mt-2 text-muted-foreground">
                    {step.body}
                  </p>
                </div>
              </div>

              <div className="hidden md:block md:w-1/2" aria-hidden />
            </motion.li>
          );
        })}
      </ol>
    </section>
  );
}

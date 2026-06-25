"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Plus } from "lucide-react";
import { useState } from "react";
import { SectionHeader } from "./SectionHeader";

const ease = [0.22, 1, 0.36, 1] as const;

const FAQS = [
  {
    q: "How is this different from call recording or our CRM?",
    a: "Your CRM logs the outcome of a visit, never the reason behind it. VoClyp analyzes the actual conversation at the scale of your whole field force and turns it into structured market intelligence: objections, demand signals, competitor mentions, and pricing reactions by region.",
  },
  {
    q: "Do agents need new devices or training?",
    a: "No. VoClyp runs on the devices your agents already use. It is one tap to start and one tap to stop, and it works offline in low-signal areas, then syncs when a connection returns.",
  },
  {
    q: "How fast do we see value?",
    a: "Most teams see real insight from their own field data within the first week of a pilot. There is no long implementation cycle.",
  },
  {
    q: "Which languages and regions are supported?",
    a: "VoClyp handles 120+ Indian languages and dialects, including mixed-language conversations, so insight is consistent across every territory and segment.",
  },
  {
    q: "Who is VoClyp built for?",
    a: "Enterprises with large field forces in FMCG and distribution, pharma, insurance and NBFC, consumer durables, automotive, real estate, building materials, and agri-inputs. It is built for sales, marketing, and product leaders who need the voice of the customer at scale.",
  },
  {
    q: "How do you handle data and privacy?",
    a: "VoClyp is permission-based and privacy-first. Data is processed and stored in India, audio is auto-deleted within hours of processing, and a recording can be deleted on demand. Compliance is built into the platform, not bolted on.",
  },
  {
    q: "What does it cost?",
    a: "Pricing is scoped to your team size and rollout. The Team plan suits a single field team getting started; Enterprise covers multi-region field forces. Book a demo for a tailored quote, and start with a free pilot.",
  },
];

export function FAQ() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section id="faq" className="section-shell border-t border-border">
      <SectionHeader
        eyebrow="FAQ"
        title="Questions decision-makers"
        highlight="ask us first."
      />

      <div className="mx-auto max-w-3xl divide-y divide-border border-y border-border">
        {FAQS.map((item, i) => {
          const isOpen = open === i;
          return (
            <div key={item.q}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : i)}
                className="flex w-full items-center justify-between gap-4 py-5 text-left"
                aria-expanded={isOpen}
              >
                <span className="text-card-title">{item.q}</span>
                <motion.span
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground"
                  animate={{ rotate: isOpen ? 45 : 0 }}
                  transition={{ duration: 0.25, ease }}
                  aria-hidden
                >
                  <Plus size={16} />
                </motion.span>
              </button>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    key="content"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3, ease }}
                    className="overflow-hidden"
                  >
                    <p className="text-body-sm pb-5 pr-11 text-muted-foreground">
                      {item.a}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </section>
  );
}

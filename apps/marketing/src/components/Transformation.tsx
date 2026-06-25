"use client";

import { ArrowRight, Check, X } from "lucide-react";
import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

const ease = [0.22, 1, 0.36, 1] as const;

const BEFORE = [
  "Field insight stays trapped in agents' heads.",
  "CRM notes capture the outcome, never the why.",
  "Market research lands months after the moment.",
  "Marketing and product guess at what customers want.",
];

const AFTER = [
  "Every visit becomes searchable market intelligence.",
  "You see the objections, demand, and competitor mentions.",
  "Signals reach your teams within minutes, not quarters.",
  "Strategy runs on real customer voice, at field scale.",
];

function useInView<T extends Element>() {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          io.disconnect();
        }
      },
      { threshold: 0.18, rootMargin: "0px 0px -48px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return { ref, inView };
}

export function Transformation() {
  const { ref, inView } = useInView<HTMLDivElement>();

  return (
    <section className="section-shell border-t border-border">
      <div ref={ref} className="site-container px-0">
        <div className="mx-auto mb-14 max-w-3xl text-center">
          <span className="eyebrow">The shift</span>
          <h2 className="text-title mt-3">
            From conversations you can&apos;t see{" "}
            <span className="text-bold-point">
              to intelligence you can act on.
            </span>
          </h2>
        </div>

        <div className="relative mx-auto grid max-w-4xl items-stretch gap-5 md:grid-cols-[1fr_auto_1fr] md:gap-4">
          <motion.div
            className="rounded-2xl border border-border bg-muted/40 p-6 sm:p-7"
            initial={{ opacity: 0, y: 20 }}
            animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
            transition={{ duration: 0.45, ease }}
          >
            <p className="eyebrow text-muted-foreground/80">Today</p>
            <p className="text-card-title mt-1 text-foreground/70">
              The intelligence leaks away
            </p>
            <ul className="mt-5 space-y-3">
              {BEFORE.map((item, i) => (
                <motion.li
                  key={item}
                  className="flex gap-3 text-body-sm text-muted-foreground"
                  initial={{ opacity: 0, x: -8 }}
                  animate={
                    inView ? { opacity: 1, x: 0 } : { opacity: 0, x: -8 }
                  }
                  transition={{ duration: 0.35, delay: 0.1 + i * 0.07, ease }}
                >
                  <span
                    className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-foreground/5 text-foreground/40"
                    aria-hidden
                  >
                    <X size={12} strokeWidth={2.5} />
                  </span>
                  <span>{item}</span>
                </motion.li>
              ))}
            </ul>
          </motion.div>

          <div className="flex items-center justify-center md:px-1">
            <motion.span
              className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-background text-indigo shadow-sm"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={
                inView
                  ? { opacity: 1, scale: 1 }
                  : { opacity: 0, scale: 0.6 }
              }
              transition={{ duration: 0.4, delay: 0.35, ease }}
              aria-hidden
            >
              <ArrowRight size={18} strokeWidth={2} className="max-md:rotate-90" />
            </motion.span>
          </div>

          <motion.div
            className="liquid-glass relative overflow-hidden rounded-2xl border border-indigo/20 p-6 shadow-sm sm:p-7"
            initial={{ opacity: 0, y: 20 }}
            animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
            transition={{ duration: 0.45, delay: 0.15, ease }}
          >
            <span
              className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo to-amber"
              aria-hidden
            />
            <p className="eyebrow text-indigo">With VoClyp</p>
            <p className="text-card-title mt-1">
              Every conversation works for you
            </p>
            <ul className="mt-5 space-y-3">
              {AFTER.map((item, i) => (
                <motion.li
                  key={item}
                  className="flex gap-3 text-body-sm text-foreground/85"
                  initial={{ opacity: 0, x: 8 }}
                  animate={inView ? { opacity: 1, x: 0 } : { opacity: 0, x: 8 }}
                  transition={{ duration: 0.35, delay: 0.25 + i * 0.07, ease }}
                >
                  <span
                    className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo/10 text-indigo"
                    aria-hidden
                  >
                    <Check size={12} strokeWidth={3} />
                  </span>
                  <span>{item}</span>
                </motion.li>
              ))}
            </ul>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

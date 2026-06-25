"use client";

import { useEffect, useRef, useState } from "react";

type Stat = {
  /** numeric target for count-up; omit for text-only value */
  to?: number;
  prefix?: string;
  suffix?: string;
  text?: string;
  label: string;
};

const STATS: Stat[] = [
  { to: 18, suffix: "%", label: "more price objections surfaced vs CRM notes" },
  { to: 3000, suffix: "+", label: "field conversations analyzed every month" },
  { text: "Minutes", label: "to insight, not the 8–12 week survey cycle" },
  { to: 120, suffix: "+", label: "Indian languages and dialects" },
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
      { threshold: 0.3 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return { ref, inView };
}

function CountUp({
  to,
  prefix = "",
  suffix = "",
  run,
}: {
  to: number;
  prefix?: string;
  suffix?: string;
  run: boolean;
}) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!run) return;
    if (typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setValue(to);
      return;
    }
    const duration = 1100;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(eased * to));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [run, to]);

  return (
    <>
      {prefix}
      {value.toLocaleString("en-IN")}
      {suffix}
    </>
  );
}

export function Stats() {
  const { ref, inView } = useInView<HTMLDivElement>();

  return (
    <section className="border-y border-border bg-muted/50 py-16">
      <div
        ref={ref}
        className="site-container grid gap-8 sm:grid-cols-2 lg:grid-cols-4"
      >
        {STATS.map((s) => (
          <div key={s.label} className="text-center">
            <p className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
              {s.to != null ? (
                <CountUp
                  to={s.to}
                  prefix={s.prefix}
                  suffix={s.suffix}
                  run={inView}
                />
              ) : (
                s.text
              )}
            </p>
            <p className="text-body-sm mt-2 text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

"use client";

import Image from "next/image";
import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

const FOUNDERS = [
  {
    name: "Kartik Chavan",
    role: "Co-founder",
    location: "Navi Mumbai",
    email: "kartik@voclyp.com",
    photo: "/founders/kartik.jpg",
    initials: "KC",
    quote:
      "In India you see how fast a field team reads the market, and how slowly that read reaches HQ. I built VoClyp to close that loop: what the field hears today should shape what product and marketing ship tomorrow.",
  },
  {
    name: "Akul Ranjan",
    role: "Co-founder",
    location: "Delhi",
    email: "akul@voclyp.com",
    photo: "/founders/akul.jpg",
    initials: "AR",
    quote:
      "The real conversation happens after the deck is put away. VoClyp captures that layer, the objections, the competitor mentions, the buying signals, and routes it to the people who can actually act on it.",
  },
] as const;

const ease = [0.22, 1, 0.36, 1] as const;

function FounderPhoto({
  src,
  alt,
  initials,
}: {
  src: string;
  alt: string;
  initials: string;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-indigo/10 text-sm font-semibold text-indigo"
        aria-hidden
      >
        {initials}
      </div>
    );
  }

  return (
    <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-full border border-border bg-muted">
      <Image
        src={src}
        alt={alt}
        fill
        className="object-cover"
        sizes="56px"
        onError={() => setFailed(true)}
      />
    </div>
  );
}

export function Founders() {
  const sectionRef = useRef<HTMLElement>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          io.disconnect();
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -48px 0px" },
    );

    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <section
      ref={sectionRef}
      className="border-t border-border py-14 md:py-16"
      aria-label="Founders"
    >
      <div className="site-container">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
          transition={{ duration: 0.4, ease }}
        >
          <p className="eyebrow mb-8 text-center">The founders</p>
        </motion.div>

        <div className="mx-auto grid max-w-4xl gap-5 md:grid-cols-2 md:gap-6">
          {FOUNDERS.map((founder, index) => (
            <motion.article
              key={founder.email}
              className="liquid-glass flex flex-col rounded-2xl border border-border/80 p-5 sm:p-6"
              initial={{ opacity: 0, y: 24 }}
              animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 24 }}
              transition={{
                duration: 0.45,
                delay: inView ? 0.12 + index * 0.1 : 0,
                ease,
              }}
            >
              <div className="mb-4 flex items-center gap-3">
                <FounderPhoto
                  src={founder.photo}
                  alt={founder.name}
                  initials={founder.initials}
                />
                <div className="min-w-0">
                  <p className="text-body-sm font-semibold">{founder.name}</p>
                  <p className="text-caption text-muted-foreground">
                    {founder.role} · {founder.location}
                  </p>
                  <a
                    href={`mailto:${founder.email}`}
                    className="text-caption text-muted-foreground underline decoration-border underline-offset-2 transition-colors hover:text-foreground hover:decoration-foreground"
                  >
                    {founder.email}
                  </a>
                </div>
              </div>
              <p className="text-body-sm leading-relaxed text-foreground/85">
                &ldquo;{founder.quote}&rdquo;
              </p>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}

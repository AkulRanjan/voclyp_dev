const SEGMENTS = [
  "FMCG & distribution",
  "Pharma field reps",
  "Insurance & NBFC",
  "Consumer durables",
  "Automotive sales",
  "Real estate",
  "Building materials",
  "Agri-inputs",
];

export function SocialProof() {
  return (
    <section className="border-y border-border py-10">
      <p className="eyebrow mb-5 text-center">Built for field sales teams across India</p>
      <div className="mask-fade-x overflow-hidden">
        <div className="animate-marquee flex w-max gap-10">
          {[...SEGMENTS, ...SEGMENTS].map((s, i) => (
            <span
              key={i}
              className="text-body-sm whitespace-nowrap font-medium text-foreground/18"
            >
              {s}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

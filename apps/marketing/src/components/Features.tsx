import { SectionReveal } from "./FadeIn";
import { SectionHeader } from "./SectionHeader";
import {
  AccountabilityVisual,
  CaptureVisual,
  CoachVisual,
} from "./FeatureVisuals";

const FEATURES = [
  {
    id: undefined,
    label: "Capture",
    title: "One tap in the field.",
    bold: "Online or offline.",
    points: [
      "Runs on the devices your agents already use.",
      "One tap to start, one tap to stop.",
      "Works offline in low-signal areas, then syncs later.",
    ],
    visual: <CaptureVisual />,
  },
  {
    id: undefined,
    label: "Market intelligence",
    title: "Hear what the market is telling you,",
    bold: "at the scale of your whole field force.",
    points: [
      "Surface demand signals, objections, and competitor mentions.",
      "Track pricing sensitivity and product feedback by region.",
      "Spot trends across every agent, territory, and segment.",
    ],
    visual: <CoachVisual />,
    flip: true,
  },
  {
    id: undefined,
    label: "Strategy & enablement",
    title: "Feed marketing, product, and sales",
    bold: "with real customer voice.",
    points: [
      "Voice-of-customer dashboards built for marketing and product.",
      "Learn what language and offers actually win deals.",
      "Coach agents on the moves your top performers make.",
    ],
    visual: <AccountabilityVisual />,
  },
];

export function Features() {
  return (
    <SectionReveal>
      <section className="border-t border-border">
        <div className="section-shell px-5 pb-0 sm:px-6 md:px-8 lg:px-12">
          <SectionHeader
            align="left"
            eyebrow="The platform"
            title="Everything your field force says,"
            highlight="working for your strategy."
          />
          {FEATURES.map((f, i) => (
            <div
              key={f.label}
              id={f.id}
              className={`grid items-center gap-10 py-14 md:grid-cols-2 md:gap-14 ${
                i < FEATURES.length - 1 ? "border-b border-border" : ""
              }`}
            >
              <div className={f.flip ? "md:order-2" : ""}>
                <span className="eyebrow">{f.label}</span>
                <h3 className="text-heading mt-3 max-w-xl">
                  {f.title}{" "}
                  <span className="text-bold-point">{f.bold}</span>
                </h3>
                <ul className="mt-5 max-w-md space-y-2.5 text-[0.9375rem] leading-relaxed text-muted-foreground">
                  {f.points.map((point) => (
                    <li key={point} className="flex gap-2.5">
                      <span
                        className="mt-[0.55rem] h-1 w-1 shrink-0 rounded-full bg-muted-foreground/45"
                        aria-hidden
                      />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className={f.flip ? "md:order-1" : ""}>{f.visual}</div>
            </div>
          ))}
        </div>
      </section>
    </SectionReveal>
  );
}

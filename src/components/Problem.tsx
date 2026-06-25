import { ClipboardList, MessageSquareOff, Timer } from "lucide-react";
import { SectionReveal } from "./FadeIn";
import { SectionHeader } from "./SectionHeader";

const CARDS = [
  {
    icon: ClipboardList,
    title: "Your CRM logs outcomes, not reasons.",
    body: "You see \"deal lost\" or \"follow-up.\" You never see what the customer actually said, or why they walked.",
  },
  {
    icon: Timer,
    title: "Surveys are slow and biased.",
    body: "By the time market research comes back, the market has already moved. Field reality never reaches the boardroom.",
  },
  {
    icon: MessageSquareOff,
    title: "Field insight dies in the field.",
    body: "What customers ask, object to, and compare you against stays in your agents' heads, invisible to marketing and product.",
  },
];

export function Problem() {
  return (
    <SectionReveal>
      <section id="product" className="section-shell">
        <SectionHeader
          eyebrow="The blind spot"
          title="Your field force is your richest research asset."
          highlight="And your darkest data hole."
        />

        <div className="grid gap-4 md:grid-cols-3">
          {CARDS.map((c) => (
            <article
              key={c.title}
              className="h-full rounded-xl border border-border bg-muted/50 p-6"
            >
              <div className="icon-tile">
                <c.icon size={18} strokeWidth={1.75} />
              </div>
              <h3 className="text-card-title mt-4">{c.title}</h3>
              <p className="text-body-sm mt-2 text-muted-foreground">{c.body}</p>
            </article>
          ))}
        </div>

        <p className="text-lead mx-auto mt-12 max-w-3xl text-center font-medium">
          Every customer conversation is market research. VoClyp makes sure it
          actually reaches your strategy.
        </p>
      </section>
    </SectionReveal>
  );
}

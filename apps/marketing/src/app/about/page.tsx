import type { Metadata } from "next";
import { Globe2, ShieldCheck, Sparkles } from "lucide-react";
import { Founders } from "@/components/Founders";
import { PageBreadcrumb } from "@/components/PageBreadcrumb";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "About VoClyp",
  description:
    "VoClyp turns field-sales conversations into market intelligence. Learn why we are building it, what we believe, and who is behind it.",
};

const VALUES = [
  {
    icon: Sparkles,
    title: "Signal over noise",
    body: "The market is already telling you what it wants. We are obsessed with surfacing that signal clearly, so teams act on truth, not hunches.",
  },
  {
    icon: ShieldCheck,
    title: "Trust is the product",
    body: "Conversation data is sensitive. Privacy, permission, and India-first storage are not features we added. They are the foundation we started from.",
  },
  {
    icon: Globe2,
    title: "Built in India, for the world",
    body: "We start with the languages and field realities of India, and design every layer to plug into companies and industries anywhere.",
  },
];

export default function AboutPage() {
  return (
    <main className="pt-32">
      <PageBreadcrumb current="About" />
      <section className="site-container">
        <div className="mx-auto max-w-3xl text-center">
          <span className="eyebrow">About VoClyp</span>
          <h1 className="text-display mt-4 text-balance">
            The market speaks in the field.{" "}
            <span className="bg-gradient-to-r from-indigo via-indigo/70 to-amber bg-clip-text text-transparent">
              We help you listen.
            </span>
          </h1>
          <p className="text-lead mx-auto mt-6 max-w-2xl text-muted-foreground">
            Every day, field teams have thousands of conversations that hold the
            clearest read on what customers want. VoClyp captures that voice and
            turns it into intelligence your marketing, product, and sales teams
            can act on.
          </p>
        </div>
      </section>

      <section className="section-shell">
        <div className="mx-auto grid max-w-4xl gap-10 md:grid-cols-2">
          <div>
            <h2 className="text-title">Why we exist</h2>
          </div>
          <div className="space-y-4 text-body-sm leading-relaxed text-muted-foreground">
            <p>
              CRMs log outcomes. Surveys arrive late and filtered. Meanwhile the
              richest market research a company owns, the raw voice of its
              customers, evaporates the moment a field visit ends.
            </p>
            <p>
              We started VoClyp because that felt backwards. The people closest
              to the customer should be the loudest input into strategy, not the
              quietest. So we built a way to capture field conversations
              responsibly and turn them into structured, usable intelligence.
            </p>
            <p>
              Today VoClyp works across languages, territories, and industries,
              and it is designed to plug into the tools companies already run on.
            </p>
          </div>
        </div>
      </section>

      <section className="section-shell border-t border-border bg-muted/40">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-title mb-10 text-center">What we believe</h2>
          <div className="grid gap-5 md:grid-cols-3">
            {VALUES.map(({ icon: Icon, title, body }) => (
              <div
                key={title}
                className="rounded-2xl border border-border bg-background p-6"
              >
                <span className="icon-tile">
                  <Icon size={18} strokeWidth={1.75} />
                </span>
                <h3 className="text-card-title mt-4">{title}</h3>
                <p className="text-body-sm mt-2 text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <Founders />

      <section className="section-shell border-t border-border">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-title">
            Want to see what your field is{" "}
            <span className="text-bold-point">actually telling you?</span>
          </h2>
          <p className="text-body-sm mt-4 text-muted-foreground">
            Book a short call and we will show you insights from real field data.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button href="/#book" variant="primary">
              Book a 15-min discovery call
            </Button>
            <Button href="/#demo" variant="secondary">
              Watch the live demo
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}

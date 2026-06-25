import { Button } from "@/components/ui/button";
import AnimatedTextCycle from "@/components/ui/animated-text-cycle";
import { WavesBackground } from "@/components/ui/waves-background";

export function Hero() {
  return (
    <header className="relative isolate flex min-h-[88vh] flex-col items-center justify-center overflow-hidden pb-20 pt-32 text-center">
      <div className="absolute inset-0 -z-10 w-full [mask-image:radial-gradient(120%_85%_at_50%_45%,#000_55%,transparent_100%)]">
        <WavesBackground />
      </div>

      <div className="site-container flex flex-col items-center">
      <span className="hero-in-1 inline-flex items-center gap-2 rounded-full border border-border bg-background/60 px-3.5 py-1.5 backdrop-blur">
        <span className="h-1.5 w-1.5 rounded-full bg-amber" aria-hidden />
        <span className="eyebrow">Field-sales conversation intelligence</span>
      </span>

      <h1 className="text-display hero-in-2 mt-7 w-full max-w-4xl text-balance">
        Turn field conversations into{" "}
        <span className="bg-gradient-to-r from-indigo via-indigo/70 to-amber bg-clip-text text-transparent">
          market intelligence
        </span>{" "}
        your teams act on.
      </h1>

      <div className="hero-in-2 mt-6 flex justify-center">
        <p className="inline-flex items-baseline text-[1.25rem] font-medium tracking-tight sm:text-[1.375rem]">
          <span className="shrink-0 text-muted-foreground">Now you can&nbsp;</span>
          <AnimatedTextCycle
            words={[
              "hear what the market wants.",
              "see why deals are won.",
              "turn talk into strategy.",
            ]}
            interval={2800}
            className="text-bold-point"
          />
        </p>
      </div>

      <p className="hero-in-3 mx-auto mt-6 max-w-2xl text-base leading-relaxed text-foreground/60 sm:text-lg">
        Your agents hold thousands of conversations a month. VoClyp captures what
        customers actually say in the field, with permission, and surfaces the
        objections, demand, and competitor signals your marketing, product, and
        sales leaders never see.
      </p>

      <div className="hero-in-3 mt-9 flex flex-wrap items-center justify-center gap-3">
        <Button href="/#book" variant="primary">
          Book a 15-min discovery call
        </Button>
        <Button href="/how-it-works" variant="secondary">
          See how it works
        </Button>
      </div>

      <p className="hero-in-3 text-caption mt-8 flex flex-wrap items-center justify-center gap-x-2.5 gap-y-1 text-muted-foreground">
        <span>Privacy-first</span>
        <span className="text-border" aria-hidden>
          /
        </span>
        <span>Stored in India</span>
        <span className="text-border" aria-hidden>
          /
        </span>
        <span>Enterprise-ready</span>
      </p>
      </div>
    </header>
  );
}

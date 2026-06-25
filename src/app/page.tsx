import { Hero } from "@/components/Hero";
import { SocialProof } from "@/components/SocialProof";
import { Problem } from "@/components/Problem";
import { Transformation } from "@/components/Transformation";
import { LiveDemo } from "@/components/LiveDemo";
import { Features } from "@/components/Features";
import { HowItWorks } from "@/components/HowItWorks";
import { Stats } from "@/components/Stats";
import { Comparison } from "@/components/Comparison";
import { Privacy } from "@/components/Privacy";
import { Pilot } from "@/components/Pilot";
import { FAQ } from "@/components/FAQ";
import { FinalCTA } from "@/components/FinalCTA";

export default function Home() {
  return (
    <main>
      <Hero />
      <SocialProof />
      <Problem />
      <Transformation />
      <LiveDemo />
      <Features />
      <HowItWorks />
      <Stats />
      <Comparison />
      <Privacy />
      <Pilot />
      <FAQ />
      <FinalCTA />
    </main>
  );
}

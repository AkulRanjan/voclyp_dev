"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  Check,
  Clock,
  Loader2,
  Play,
  RotateCcw,
  Smartphone,
  Target,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { SectionHeader } from "./SectionHeader";

const ease = [0.22, 1, 0.36, 1] as const;

type SignalType = "Need" | "Demand" | "Competitor" | "Buying signal";

type Turn = {
  speaker: "Agent" | "Customer";
  hi: string;
  en: string;
};

type ExtractedSignal = { type: SignalType; label: string };

const SCRIPT: Turn[] = [
  {
    speaker: "Agent",
    hi: "नमस्ते! आज किस तरह का मैट्रेस देख रहे हैं?",
    en: "Hello! What kind of mattress are you looking for today?",
  },
  {
    speaker: "Customer",
    hi: "पीठ में दर्द रहता है, डॉक्टर ने ऑर्थोपेडिक सलाह दी है।",
    en: "I have back pain; my doctor suggested an orthopaedic mattress.",
  },
  {
    speaker: "Customer",
    hi: "बजट ज़्यादा नहीं है, पर अच्छी क्वालिटी चाहिए।",
    en: "Budget isn't high, but I want good quality.",
  },
  {
    speaker: "Customer",
    hi: "पड़ोसी ने स्थानीय ब्रांड लिया था, छह महीने में धंस गया।",
    en: "My neighbour bought a local brand; it sagged in six months.",
  },
  {
    speaker: "Agent",
    hi: "समझ गया। चलिए कुछ भरोसेमंद ऑप्शन दिखाता हूँ।",
    en: "Got it. Let me show you some reliable options.",
  },
  {
    speaker: "Customer",
    hi: "अगर ट्रायल और EMI मिल जाए तो आज ही ले लूँगा।",
    en: "If I get a trial period and EMI, I'll buy today.",
  },
];

const EXTRACTED_SIGNALS: ExtractedSignal[] = [
  { type: "Need", label: "Back pain · orthopaedic support" },
  { type: "Demand", label: "Quality-first · budget-conscious" },
  { type: "Competitor", label: "Local brand · sagging in 6 months" },
  { type: "Buying signal", label: "Trial + EMI → ready to close" },
];

const SIGNAL_STYLES: Record<SignalType, { dot: string; chip: string; text: string }> = {
  Need: { dot: "bg-indigo", chip: "border-indigo/25 bg-indigo/[0.06]", text: "text-indigo" },
  Demand: { dot: "bg-amber", chip: "border-amber/30 bg-amber/10", text: "text-amber-700" },
  Competitor: { dot: "bg-foreground/40", chip: "border-border bg-muted", text: "text-foreground/70" },
  "Buying signal": {
    dot: "bg-emerald-500",
    chip: "border-emerald-500/25 bg-emerald-500/[0.08]",
    text: "text-emerald-600",
  },
};

const PROCESSING_STEPS = [
  "Transcribing conversation",
  "Translating to English",
  "Extracting signals",
  "Building reports",
];

const STEP_MS = 2800;
const PROCESS_STEP_MS = 900;

type Phase = "idle" | "recording" | "processing" | "complete";
type TabId = "customer" | "agent" | "teams";

const TABS: { id: TabId; label: string; icon: typeof Smartphone }[] = [
  { id: "customer", label: "For the customer", icon: Smartphone },
  { id: "agent", label: "For the agent", icon: Target },
  { id: "teams", label: "For your teams", icon: BarChart3 },
];

const RECOMMENDATIONS = [
  { name: "OrthoRest 8\"", tags: ["Orthopaedic", "₹1,499/mo EMI"], match: 96 },
  { name: "SleepWell Spine", tags: ["100-night trial", "10-yr warranty"], match: 93 },
  { name: "ComfortPlus Dual", tags: ["Firm support", "Best value"], match: 89 },
];

const AGENT_ACTIONS = [
  "Lead with orthopaedic spine support and doctor-recommended firmness.",
  "Counter the local-brand worry with the 10-year non-sag warranty.",
  "Offer the 100-night trial and 6-month no-cost EMI.",
  "If undecided, follow up in 2 days with the OrthoRest quote.",
];

const TEAM_SIGNALS = [
  "Orthopaedic mattress demand up in this territory this month.",
  "Local-brand sagging complaints: 4th this week.",
  "Trial-period requests rising among first-time buyers.",
];

export function LiveDemo() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [step, setStep] = useState(0);
  const [processStep, setProcessStep] = useState(0);
  const [visibleSignals, setVisibleSignals] = useState(0);
  const [tab, setTab] = useState<TabId>("customer");
  const reduced = useRef(false);

  useEffect(() => {
    reduced.current =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }, []);

  function start() {
    setTab("customer");
    setProcessStep(0);
    setVisibleSignals(0);
    if (reduced.current) {
      setStep(SCRIPT.length);
      setPhase("complete");
      setVisibleSignals(EXTRACTED_SIGNALS.length);
      return;
    }
    setStep(1);
    setPhase("recording");
  }

  useEffect(() => {
    if (phase !== "recording") return;
    if (step >= SCRIPT.length) {
      setPhase("processing");
      setProcessStep(0);
      return;
    }
    const t = setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => clearTimeout(t);
  }, [phase, step]);

  useEffect(() => {
    if (phase !== "processing") return;
    if (processStep >= PROCESSING_STEPS.length) {
      setPhase("complete");
      setVisibleSignals(0);
      return;
    }
    const t = setTimeout(() => setProcessStep((s) => s + 1), PROCESS_STEP_MS);
    return () => clearTimeout(t);
  }, [phase, processStep]);

  useEffect(() => {
    if (phase !== "complete") return;
    if (visibleSignals >= EXTRACTED_SIGNALS.length) return;
    const t = setTimeout(() => setVisibleSignals((s) => s + 1), 400);
    return () => clearTimeout(t);
  }, [phase, visibleSignals]);

  const turns = SCRIPT.slice(0, phase === "idle" ? 0 : step);
  const isRecording = phase === "recording";
  const isProcessing = phase === "processing";
  const isComplete = phase === "complete";
  const processProgress = Math.round(
    (processStep / PROCESSING_STEPS.length) * 100,
  );

  return (
    <section id="demo" className="section-shell border-t border-border">
      <SectionHeader
        eyebrow="See it in action"
        title="One Hindi sales visit becomes"
        highlight="intelligence everyone can use."
      />

      <div className="mx-auto max-w-5xl">
        {phase === "idle" ? (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease }}
            className="relative overflow-hidden rounded-3xl border border-border bg-muted/40"
          >
            <div
              className="pointer-events-none absolute inset-0 opacity-70 [mask-image:radial-gradient(120%_90%_at_50%_0%,#000_30%,transparent_75%)]"
              style={{
                backgroundImage:
                  "radial-gradient(60% 60% at 20% 0%, rgba(61,43,255,0.10), transparent), radial-gradient(50% 50% at 90% 10%, rgba(255,179,71,0.12), transparent)",
              }}
              aria-hidden
            />
            <div className="relative flex flex-col items-center px-6 py-16 text-center sm:py-20">
              <button
                type="button"
                onClick={start}
                className="group relative flex h-16 w-16 items-center justify-center rounded-full bg-navy text-white transition-transform hover:scale-105"
                aria-label="Play the field visit demo"
              >
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-navy/30" />
                <Play size={22} className="relative ml-0.5" fill="currentColor" />
              </button>
              <p className="text-card-title mt-6">Play a real field visit</p>
              <p className="text-body-sm mt-2 max-w-md text-muted-foreground">
                A customer shopping for a mattress, in Hindi. The visit records
                first. When it ends, VoClyp analyzes the conversation and
                delivers reports for the customer, agent, and your teams.
              </p>
              <span className="text-caption mt-5 inline-flex items-center gap-2 rounded-full border border-border bg-background px-3 py-1 font-medium text-muted-foreground">
                <span className="h-1.5 w-1.5 rounded-full bg-amber" aria-hidden />
                Record → analyze → deliver
              </span>
            </div>
          </motion.div>
        ) : (
          <div className="space-y-5">
            <div className="grid items-stretch gap-5 lg:grid-cols-2">
              {/* Transcript */}
              <div className="flex flex-col rounded-2xl border border-border bg-background p-5 sm:p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="relative flex h-2.5 w-2.5" aria-hidden>
                      {isRecording && (
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500/60" />
                      )}
                      <span
                        className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                          isRecording ? "bg-red-500" : "bg-muted-foreground/40"
                        }`}
                      />
                    </span>
                    <span className="text-caption font-medium text-muted-foreground">
                      {isRecording
                        ? "Recording field visit"
                        : "Visit captured"}
                    </span>
                  </div>
                  <Waveform active={isRecording} />
                </div>

                <div className="mt-5 flex-1 space-y-3">
                  <AnimatePresence initial={false}>
                    {turns.map((turn, i) => {
                      const isCustomer = turn.speaker === "Customer";
                      return (
                        <motion.div
                          key={i}
                          layout
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.45, ease }}
                          className={`flex ${isCustomer ? "justify-start" : "justify-end"}`}
                        >
                          <div
                            className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 ${
                              isCustomer
                                ? "rounded-tl-sm bg-muted text-foreground/85"
                                : "rounded-tr-sm bg-navy text-white/90"
                            }`}
                          >
                            <span
                              className={`mb-0.5 block text-[0.6875rem] font-medium uppercase tracking-wide ${
                                isCustomer ? "text-muted-foreground" : "text-white/45"
                              }`}
                            >
                              {turn.speaker}
                            </span>
                            <span className="text-[0.9375rem] leading-relaxed">
                              {turn.hi}
                            </span>
                            <span
                              className={`mt-1 block text-caption italic ${
                                isCustomer ? "text-muted-foreground/80" : "text-white/55"
                              }`}
                            >
                              {turn.en}
                            </span>
                          </div>
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                </div>

                {isRecording && step < SCRIPT.length && (
                  <p className="text-caption mt-5 text-muted-foreground/70">
                    Analysis runs after the visit ends.
                  </p>
                )}
                {!isRecording && (
                  <p className="text-caption mt-5 text-muted-foreground/70">
                    Audio is auto-deleted after processing. Only the insight
                    remains.
                  </p>
                )}
              </div>

              {/* Analysis panel */}
              <div className="flex flex-col rounded-2xl border border-indigo/15 bg-muted/40 p-5 sm:p-6">
                <div className="flex items-center justify-between gap-3">
                  <span className="eyebrow">VoClyp analysis</span>
                  {isComplete && (
                    <button
                      type="button"
                      onClick={start}
                      className="text-caption inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 font-medium text-muted-foreground transition-colors hover:text-foreground"
                    >
                      <RotateCcw size={12} />
                      Replay
                    </button>
                  )}
                </div>

                {isRecording && (
                  <div className="mt-6 flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-border px-6 py-12 text-center">
                    <Clock size={28} className="text-muted-foreground/40" />
                    <p className="text-body-sm mt-4 font-medium text-muted-foreground">
                      Waiting for visit to end
                    </p>
                    <p className="text-caption mt-2 max-w-[220px] text-muted-foreground/80">
                      Transcription and insight extraction begin once the
                      conversation is complete.
                    </p>
                  </div>
                )}

                {isProcessing && (
                  <div className="mt-4 flex flex-1 flex-col">
                    <div className="flex items-center gap-2 text-body-sm font-medium text-foreground/85">
                      <Loader2 size={16} className="animate-spin text-indigo" />
                      Analyzing conversation…
                    </div>
                    <div className="mt-4">
                      <div className="flex items-center justify-between text-caption text-muted-foreground">
                        <span>Processing</span>
                        <span className="tabular-nums">{processProgress}%</span>
                      </div>
                      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-border">
                        <motion.div
                          className="h-full rounded-full bg-gradient-to-r from-indigo to-amber"
                          animate={{ width: `${processProgress}%` }}
                          transition={{ duration: 0.5, ease }}
                        />
                      </div>
                    </div>
                    <ul className="mt-5 space-y-2">
                      {PROCESSING_STEPS.map((label, i) => {
                        const done = i < processStep;
                        const active = i === processStep;
                        return (
                          <li
                            key={label}
                            className={`text-body-sm flex items-center gap-2.5 ${
                              done || active
                                ? "text-foreground/85"
                                : "text-muted-foreground/50"
                            }`}
                          >
                            {done ? (
                              <Check size={14} className="text-indigo" />
                            ) : active ? (
                              <Loader2 size={14} className="animate-spin text-indigo" />
                            ) : (
                              <span className="h-3.5 w-3.5 rounded-full border border-border" />
                            )}
                            {label}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}

                {isComplete && (
                  <>
                    <p className="text-caption mt-3 text-muted-foreground">
                      Analysis complete
                    </p>
                    <div className="mt-4 flex-1 space-y-2.5">
                      <AnimatePresence initial={false}>
                        {EXTRACTED_SIGNALS.slice(0, visibleSignals).map((s, i) => {
                          const style = SIGNAL_STYLES[s.type];
                          return (
                            <motion.div
                              key={`${s.type}-${i}`}
                              layout
                              initial={{ opacity: 0, x: 14, scale: 0.96 }}
                              animate={{ opacity: 1, x: 0, scale: 1 }}
                              transition={{ duration: 0.45, ease }}
                              className={`flex items-start gap-3 rounded-xl border px-3.5 py-3 ${style.chip}`}
                            >
                              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${style.dot}`} />
                              <div>
                                <p className={`text-caption font-semibold uppercase tracking-wide ${style.text}`}>
                                  {s.type}
                                </p>
                                <p className="text-body-sm mt-0.5 text-foreground/85">
                                  {s.label}
                                </p>
                              </div>
                            </motion.div>
                          );
                        })}
                      </AnimatePresence>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Deliverables — only after analysis + signals */}
            <AnimatePresence>
              {isComplete && visibleSignals >= EXTRACTED_SIGNALS.length && (
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, ease }}
                  className="rounded-2xl border border-border bg-background p-5 sm:p-6"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <span className="eyebrow text-indigo">Reports generated</span>
                      <p className="text-card-title mt-1">
                        From one 5-minute visit
                      </p>
                    </div>
                    <span className="text-caption inline-flex items-center gap-1.5 rounded-full border border-emerald-500/25 bg-emerald-500/[0.08] px-3 py-1 font-medium text-emerald-600">
                      <Clock size={12} />
                      Ready in minutes
                    </span>
                  </div>

                  <div className="mt-5 flex flex-wrap gap-2">
                    {TABS.map((t) => {
                      const active = tab === t.id;
                      return (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => setTab(t.id)}
                          className={`text-body-sm inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 font-medium transition-colors ${
                            active
                              ? "border-navy bg-navy text-white"
                              : "border-border text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          <t.icon size={15} />
                          {t.label}
                        </button>
                      );
                    })}
                  </div>

                  <div className="mt-5">
                    <AnimatePresence mode="wait">
                      <motion.div
                        key={tab}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={{ duration: 0.3, ease }}
                      >
                        {tab === "customer" && <CustomerReport />}
                        {tab === "agent" && <AgentPlaybook />}
                        {tab === "teams" && <TeamSignals />}
                      </motion.div>
                    </AnimatePresence>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </section>
  );
}

function CustomerReport() {
  return (
    <div className="rounded-xl border border-indigo/15 bg-muted/30 p-5">
      <div className="flex items-center gap-2 text-caption text-muted-foreground">
        <Smartphone size={14} className="text-indigo" />
        Sent to Rahul on WhatsApp, a few minutes after the visit
      </div>
      <p className="text-card-title mt-2">3 mattresses matched to your needs</p>
      <div className="mt-4 space-y-2.5">
        {RECOMMENDATIONS.map((r) => (
          <div
            key={r.name}
            className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3.5 py-3"
          >
            <div>
              <p className="text-body-sm font-semibold">{r.name}</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {r.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-caption rounded-full bg-muted px-2 py-0.5 text-muted-foreground"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
            <div className="text-right">
              <p className="text-body-sm font-semibold text-indigo tabular-nums">
                {r.match}%
              </p>
              <p className="text-caption text-muted-foreground">match</p>
            </div>
          </div>
        ))}
      </div>
      <p className="text-caption mt-4 text-muted-foreground">
        Chosen for orthopaedic support, trial period, and EMI, exactly what Rahul
        asked for.
      </p>
    </div>
  );
}

function AgentPlaybook() {
  return (
    <div className="rounded-xl border border-border bg-muted/30 p-5">
      <div className="flex items-center gap-2 text-caption text-muted-foreground">
        <Target size={14} className="text-indigo" />
        Next best actions, delivered after analysis
      </div>
      <ul className="mt-4 space-y-2.5">
        {AGENT_ACTIONS.map((a) => (
          <li
            key={a}
            className="flex items-start gap-3 rounded-lg border border-border bg-background px-3.5 py-3"
          >
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo/10 text-indigo">
              <Check size={12} strokeWidth={3} />
            </span>
            <span className="text-body-sm text-foreground/85">{a}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TeamSignals() {
  return (
    <div className="rounded-xl border border-border bg-muted/30 p-5">
      <div className="flex items-center gap-2 text-caption text-muted-foreground">
        <BarChart3 size={14} className="text-indigo" />
        Aggregated across every visit, routed to marketing and product
      </div>
      <ul className="mt-4 space-y-2.5">
        {TEAM_SIGNALS.map((s) => (
          <li
            key={s}
            className="flex items-start gap-3 rounded-lg border border-border bg-background px-3.5 py-3"
          >
            <ArrowRight size={15} className="mt-0.5 shrink-0 text-amber" />
            <span className="text-body-sm text-foreground/85">{s}</span>
          </li>
        ))}
      </ul>
      <p className="text-caption mt-4 text-muted-foreground">
        Weekly territory and market reports are compiled from these signals
        automatically.
      </p>
    </div>
  );
}

function Waveform({ active }: { active: boolean }) {
  const bars = [0.4, 0.8, 0.5, 1, 0.6, 0.9, 0.45];
  return (
    <div className="flex items-center gap-[3px]" aria-hidden>
      {bars.map((h, i) => (
        <motion.span
          key={i}
          className="w-[3px] rounded-full bg-indigo/60"
          animate={
            active
              ? { height: [`${h * 8}px`, `${h * 18}px`, `${h * 8}px`] }
              : { height: "5px" }
          }
          transition={{
            duration: 1.1,
            repeat: active ? Infinity : 0,
            delay: i * 0.08,
            ease: "easeInOut",
          }}
          style={{ height: "8px" }}
        />
      ))}
    </div>
  );
}

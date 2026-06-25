"use client";

import { Check, Minus, X } from "lucide-react";
import { motion } from "framer-motion";
import { SectionHeader } from "./SectionHeader";

const ease = [0.22, 1, 0.36, 1] as const;

type Cell = "yes" | "no" | "partial" | string;

const COLUMNS = ["Notebooks & memory", "CRM notes", "Surveys", "VoClyp"] as const;

const ROWS: { label: string; cells: [Cell, Cell, Cell, Cell] }[] = [
  {
    label: "Captures why a deal moves, not just the outcome",
    cells: ["no", "no", "partial", "yes"],
  },
  {
    label: "Works at the scale of your whole field force",
    cells: ["no", "no", "no", "yes"],
  },
  {
    label: "Surfaces objections and competitor mentions",
    cells: ["no", "no", "partial", "yes"],
  },
  {
    label: "Tracks demand and pricing trends by region",
    cells: ["no", "partial", "partial", "yes"],
  },
  {
    label: "Speed from conversation to insight",
    cells: ["—", "Days", "8–12 weeks", "Minutes"],
  },
];

function CellMark({ value }: { value: Cell }) {
  if (value === "yes")
    return (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-indigo/10 text-indigo">
        <Check size={14} strokeWidth={3} />
      </span>
    );
  if (value === "no")
    return (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-foreground/5 text-foreground/35">
        <X size={14} strokeWidth={2.5} />
      </span>
    );
  if (value === "partial")
    return (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-amber/15 text-amber-700">
        <Minus size={14} strokeWidth={3} />
      </span>
    );
  return <span className="text-body-sm font-medium">{value}</span>;
}

export function Comparison() {
  return (
    <section className="section-shell border-t border-border">
      <div className="mx-auto max-w-4xl">
        <SectionHeader
          align="left"
          eyebrow="Why VoClyp"
          title="The market signal is already there."
          highlight="Nothing else captures it."
        />

        <motion.div
          className="overflow-x-auto"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "0px 0px -80px 0px" }}
          transition={{ duration: 0.5, ease }}
        >
        <table className="w-full min-w-[640px] border-separate border-spacing-0">
          <thead>
            <tr>
              <th className="w-[40%] p-4 text-left" aria-hidden />
              {COLUMNS.map((col) => {
                const isVoClyp = col === "VoClyp";
                return (
                  <th
                    key={col}
                    className={`p-4 text-center align-bottom ${
                      isVoClyp
                        ? "rounded-t-xl border-x border-t border-indigo/25 bg-indigo/[0.04]"
                        : ""
                    }`}
                  >
                    <span
                      className={`text-card-title ${
                        isVoClyp ? "text-indigo" : "text-muted-foreground"
                      }`}
                    >
                      {col}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row, r) => (
              <tr key={row.label}>
                <td className="border-t border-border p-4 text-body-sm text-foreground/85">
                  {row.label}
                </td>
                {row.cells.map((cell, c) => {
                  const isVoClyp = c === COLUMNS.length - 1;
                  const isLast = r === ROWS.length - 1;
                  return (
                    <td
                      key={c}
                      className={`border-t border-border p-4 text-center ${
                        isVoClyp
                          ? `border-x border-indigo/25 bg-indigo/[0.04] ${
                              isLast ? "rounded-b-xl border-b" : ""
                            }`
                          : ""
                      }`}
                    >
                      <span className="flex items-center justify-center">
                        <CellMark value={cell} />
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        </motion.div>
      </div>
    </section>
  );
}

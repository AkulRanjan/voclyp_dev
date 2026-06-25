"use client";

import { useState, type FormEvent } from "react";

type Status = "idle" | "submitting" | "success" | "error";

export function FinalCTA() {
  const [contact, setContact] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!contact.trim()) return;
    setStatus("submitting");
    setMessage("");
    try {
      const res = await fetch("/api/demo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contact }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus("error");
        setMessage(data.error ?? "Something went wrong. Try again.");
        return;
      }
      try {
        const leads = JSON.parse(localStorage.getItem("voclyp_leads") || "[]");
        leads.push({ contact, ts: new Date().toISOString() });
        localStorage.setItem("voclyp_leads", JSON.stringify(leads));
      } catch {
        /* storage unavailable */
      }
      setStatus("success");
      setMessage(data.message);
    } catch {
      setStatus("error");
      setMessage("Network error. Please try again.");
    }
  }

  return (
    <section id="book" className="section-shell border-t border-border">
      <div className="mx-auto max-w-3xl text-center">
        <h2 className="text-title">
          Your agents had thousands of conversations this month.{" "}
          <span className="text-bold-point">
            What is the market actually telling you?
          </span>
        </h2>
        <p className="text-body-sm mt-5 text-muted-foreground">
          Book a demo. See insights from your own field data within a week. Early
          partners get a free pilot.
        </p>

        {status === "success" ? (
          <p className="text-lead mt-10 font-semibold">{message}</p>
        ) : (
          <form
            onSubmit={handleSubmit}
            className="mx-auto mt-10 flex max-w-md flex-col gap-3 sm:flex-row"
          >
            <input
              type="text"
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              placeholder="Work email or phone"
              aria-label="Work email or phone"
              required
              className="text-body-sm flex-1 rounded-full border border-border bg-background px-5 py-3 placeholder:text-muted-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-foreground/20"
            />
            <button
              type="submit"
              disabled={status === "submitting"}
              className="text-body-sm rounded-full bg-amber px-6 py-3 font-semibold text-[#1a1205] transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              {status === "submitting" ? "Booking…" : "Book a demo"}
            </button>
          </form>
        )}

        {status === "error" && (
          <p className="text-body-sm mt-3 text-red-600">{message}</p>
        )}

        <p className="text-caption mt-6 text-muted-foreground">
          No spam. No commitment. Just a look at what your market is actually
          saying.
        </p>
      </div>
    </section>
  );
}

"""Deterministic conversation scoring derived from extracted signals.

The score is a transparent, explainable heuristic over the universal signal
taxonomy — not a black box. Buying intent, explicit demand, and commitments
push the score up; objections, price pushback, and competitor mentions pull it
down. It exists so the dashboards (store, rep, area) have a single comparable,
aggregatable measure per conversation.

This is the Phase-1 scorer; like the signal extractor it is built to be swapped
for a learned model later (same inputs — the signal list — same output shape),
so nothing downstream (analytics, rankings, the mobile app) changes when it is.
"""
from __future__ import annotations

# Weight per occurrence of each signal type, applied to a neutral baseline.
# Tuned so a clean buying conversation lands in "Good" and an objection-heavy
# one in "Poor"; the universal taxonomy types are the only inputs.
_SIGNAL_WEIGHTS = {
    "intent": 12.0,
    "demand": 10.0,
    "promise": 15.0,
    "objection": -8.0,
    "price_reaction": -6.0,
    "competitor_mention": -4.0,
}
# Extra points for high-value *specific* moments, on top of the per-type weight.
# These let the score reflect more than raw signal counts: a clear NPS/referral
# ("sabko recommend karunga"), a firm buying commitment, or a booked trial are
# worth more than a generic mention.
_SUBTYPE_BONUS = {
    "referral_intent": 10.0,   # NPS-style advocacy — the customer will promote us
    "purchase_intent": 6.0,    # explicit "I'll buy / book it"
    "trial_request": 3.0,      # booked a trial / 100-night test
    "delivery_promise": 3.0,   # rep locked a concrete delivery commitment
    "follow_up_promise": 1.0,
}
_BASELINE = 50.0

RATINGS = ("Poor", "Average", "Good")
OUTCOMES = ("at_risk", "neutral", "promising")


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _signal_type(signal) -> str:
    return signal["type"] if isinstance(signal, dict) else signal.type


def _signal_subtype(signal) -> str:
    if isinstance(signal, dict):
        return signal.get("subtype") or ""
    return getattr(signal, "subtype", "") or ""


def score_conversation(signals) -> dict:
    """Score a conversation from its signal list.

    Pure and deterministic: the same signals always yield the same result.
    Accepts either Signal dataclasses or plain dicts with a ``type`` key.
    Returns the block embedded in the insight doc under ``scoring``.
    """
    counts = {t: 0 for t in _SIGNAL_WEIGHTS}
    subtype_counts: dict[str, int] = {}
    demand_subtypes: set[str] = set()
    bonus = 0.0
    for signal in signals:
        s_type = _signal_type(signal)
        if s_type in counts:
            counts[s_type] += 1
        sub = _signal_subtype(signal)
        if sub:
            subtype_counts[sub] = subtype_counts.get(sub, 0) + 1
            bonus += _SUBTYPE_BONUS.get(sub, 0.0)
            if s_type == "demand":
                demand_subtypes.add(sub)

    score = _BASELINE + sum(_SIGNAL_WEIGHTS[t] * n for t, n in counts.items()) + bonus
    score = round(_clamp(score), 1)

    if score >= 70:
        rating = "Good"
    elif score >= 45:
        rating = "Average"
    else:
        rating = "Poor"

    positive = counts["intent"] + counts["demand"] + counts["promise"]
    negative = counts["objection"] + counts["price_reaction"]
    if counts["promise"] or (positive > negative and score >= 60):
        outcome = "promising"
    elif negative > positive and score < 45:
        outcome = "at_risk"
    else:
        outcome = "neutral"

    return {
        "score": score,
        "rating": rating,
        "outcome": outcome,
        "signal_counts": counts,
        "subtype_counts": subtype_counts,
        # Grounded sub-measures the dashboards surface; each maps directly to
        # signal occurrences, so they are explainable, not invented.
        "components": {
            "buying_intent": counts["intent"] + counts["demand"],
            "commitment": counts["promise"],
            "objection_pressure": counts["objection"] + counts["price_reaction"],
            "competitive_pressure": counts["competitor_mention"],
            # NPS-style advocacy: the customer said they'd recommend us.
            "advocacy": subtype_counts.get("referral_intent", 0),
            # Discovery depth: how many distinct needs the rep surfaced.
            "discovery_depth": len(demand_subtypes),
        },
    }

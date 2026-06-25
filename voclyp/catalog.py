"""Product catalog loading for tenant verticals."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_CATALOG_DIR = Path(
    os.environ.get("VOCLYP_CATALOG_DIR")
    or Path(__file__).resolve().parents[1] / "configs" / "catalogs"
)


def load_catalog(industry: str, catalog_dir=None) -> dict:
    catalog_dir = Path(catalog_dir) if catalog_dir else DEFAULT_CATALOG_DIR
    path = catalog_dir / f"{industry}.json"
    if not path.exists():
        raise FileNotFoundError(f"no catalog for '{industry}' at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _signal_profile(signals: list[dict]) -> dict:
    """Derive customer needs + budget posture from extracted signals.

    Reads both the structured (type, subtype) and the free-text quote, so it
    works whether the signal taxonomy fired or the rep simply said the words.
    """
    subtypes = {(s.get("subtype") or "").lower() for s in signals}
    text = " ".join(
        (s.get("quote") or "") + " " + (s.get("subtype") or "") + " " + (s.get("type") or "")
        for s in signals
    ).lower()

    def any_in(*needles: str) -> bool:
        return any(n in text for n in needles)

    return {
        "text": text,
        "subtypes": subtypes,
        "ortho": "orthopaedic_need" in subtypes or any_in("back pain", "spine", "orthopaed", "orthoped", "कमर", "पीठ", "दर्द", "doctor"),
        "cooling": "cooling_need" in subtypes or any_in("cooling", "hot sleeper", "gel", "garmi", "गर्मी", "sweat", "warm"),
        "wants_soft": any_in("soft", "plush", "नरम", "luxurious", "luxury", "comfort"),
        "wants_firm": any_in("firm", "hard", "कठोर", "support"),
        "budget_sensitive": bool({"budget_too_high", "budget_sensitive"} & subtypes) or any_in("budget", "expensive", "costly", "afford", "discount", "value for money", "bajat"),
        "emi_interest": bool({"emi_request", "emi_interest"} & subtypes) or any_in("emi", "installment", "किस्त", "monthly payment", "finance"),
        "trial": "trial_request" in subtypes or any_in("trial", "try first", "100 night", "ट्रायल"),
        "premium_intent": any_in("premium", "luxury", "royale", "best one", "top model"),
        "warranty": {"warranty_concern", "local_brand_sagging"} & subtypes or any_in("warranty", "sagging", "sagged", "dhans", "durability"),
    }


_TIER_AFFORDABILITY = {"entry": 12, "mid": 6, "premium": -2, "luxury": -10}
_TIER_PREMIUM = {"entry": -6, "mid": 0, "premium": 8, "luxury": 12}


def emi_line(product: dict) -> str:
    """Human-readable no-cost EMI line, e.g. 'No-cost EMI \u20b92,298/mo for 6 months'.

    Tolerant of products whose ``emi`` has already been rendered to a string by
    rank_products (idempotent), as well as raw catalog products (dict).
    """
    emi = product.get("emi")
    if isinstance(emi, str):
        return emi
    emi = emi or {}
    monthly = emi.get("monthly_inr") or product.get("emi_monthly_inr")
    if not monthly:
        return ""
    tenure = emi.get("tenure_months")
    label = "No-cost EMI" if emi.get("no_cost", True) else "EMI"
    out = f"{label} \u20b9{int(monthly):,}/mo"
    if tenure:
        out += f" for {tenure} months"
    return out


def _score_product(product: dict, profile: dict) -> tuple[int, list[str]]:
    """Return (match_score, reasons) for one product against the need profile."""
    series = (product.get("series") or "").lower()
    tier = (product.get("affordability_tier") or "mid").lower()
    score = 60
    reasons: list[str] = []

    # --- needs match (primary) ---
    if profile["ortho"]:
        if series == "ortho":
            score += 22
            reasons.append("Orthopaedic SmartGRID for back/spine support")
        else:
            score -= 8
    if profile["cooling"]:
        if product.get("cooling"):
            score += 26
            reasons.append("SnowTec cooling for hot sleepers")
        else:
            score -= 12
    if profile["wants_soft"] and series == "luxe":
        score += 14
        reasons.append("Plush medium-soft comfort")
    if profile["wants_firm"] and series == "ortho":
        score += 10
        reasons.append("Firm, supportive feel")
    if profile["warranty"]:
        score += 4
        reasons.append(f"{product.get('warranty_years', 10)}-year warranty vs sagging")

    # --- keyword overlap (secondary, taxonomy-aligned) ---
    keywords = " ".join(product.get("match_signals") or product.get("tags") or []).lower()
    overlap = sum(1 for kw in set(keywords.split()) if kw and kw in profile["text"])
    score += min(12, overlap * 4)

    # --- affordability posture ---
    if profile["budget_sensitive"]:
        score += _TIER_AFFORDABILITY.get(tier, 0)
        if tier in ("entry", "mid"):
            reasons.append("Fits a tighter budget")
    if profile["premium_intent"]:
        score += _TIER_PREMIUM.get(tier, 0)
        if tier in ("premium", "luxury"):
            reasons.append("Premium pick they asked about")
    if profile["emi_interest"]:
        line = emi_line(product)
        if line:
            reasons.append(line)
    if profile["trial"]:
        nights = product.get("trial_nights")
        if nights:
            reasons.append(f"{nights}-night trial")

    if not reasons:
        positioning = product.get("positioning")
        if positioning:
            reasons.append(positioning)

    return max(40, min(99, score)), reasons


def rank_products(catalog: dict, signals: list[dict], limit: int = 3,
                  discussed_skus: list[str] | None = None) -> list[dict]:
    """Rank catalog products by customer needs + affordability fit.

    Each returned product keeps all its catalog fields plus ``match_score``,
    a deterministic ``reasons`` list, and an ``emi`` line. Fully offline and
    deterministic; the LLM grounding layer (voclyp/recommend.py) only adds
    natural-language ``why`` text on top of this shortlist.

    ``discussed_skus`` (most-discussed first) are the products the conversation
    actually referenced — resolved by voclyp/product_mentions.py. When given,
    they lead the result in that order ("discussed-first"), each tagged with a
    "You discussed this in-store" reason, and needs-based picks follow.
    """
    products = catalog.get("products") or []
    if not products:
        return []

    profile = _signal_profile(signals or [])
    scored = []
    for p in products:
        score, reasons = _score_product(p, profile)
        scored.append({
            **p,
            "match_score": score,
            "reasons": reasons,
            "emi": emi_line(p),
        })

    # Primary: score desc. Tie-break: cheaper first, so with no signals we lead
    # with the most broadly accessible options rather than the flagship.
    scored.sort(key=lambda x: (-x["match_score"], x.get("price_inr", 0)))

    discussed = [s for s in (discussed_skus or []) if s]
    if discussed:
        by_sku = {p.get("sku"): p for p in scored}
        front: list[dict] = []
        for sku in discussed:  # preserve mention order (dominant first)
            p = by_sku.get(sku)
            if p is not None and p not in front:
                if "You discussed this in-store" not in p["reasons"]:
                    p["reasons"] = ["You discussed this in-store", *p["reasons"]]
                front.append(p)
        rest = [p for p in scored if p not in front]
        scored = front + rest

    return scored[:limit]

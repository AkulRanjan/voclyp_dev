"""Hybrid product recommendations: deterministic shortlist + grounded LLM reasoning.

Step A (always, offline): rank_products() picks the best-fit shortlist from the
real product knowledge base using customer needs + affordability.

Step B (when a Sarvam client is supplied): an LLM explains *why* each shortlisted
product fits *this* customer and drafts a personalised WhatsApp blurb. The model
is grounded strictly to the shortlist — it may not invent products, prices, or
EMI. Any LLM/parse error falls back to the deterministic reasons, exactly like
voclyp/pipeline/stages/sarvam_visit_notes.py; this function never raises.
"""
from __future__ import annotations

import json
import re

from .catalog import emi_line, rank_products

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}", re.MULTILINE)

_SYSTEM = (
    "You are a sales assistant for The Sleep Company, an Indian mattress retailer. "
    "Recommend ONLY from the provided product list. NEVER invent products, prices, "
    "EMI figures, or features that are not in the list. Use the customer's own words "
    "from the visit. Be concrete, warm, and concise. Write for an Indian customer; "
    "rupee amounts must match the list exactly. "
    "Respect what the customer actually said: if they declined EMI ('Non EMI', "
    "one-time payment) do not push EMI; if they said they have no back pain, do not "
    "claim orthopaedic need. If they picked a specific mattress, lead with it."
)

_USER_TEMPLATE = """A sales rep just finished a store visit. Recommend why these shortlisted mattresses fit this customer.

CUSTOMER SIGNALS (what they cared about; may be empty):
{signals}

PRODUCTS THE CUSTOMER LOOKED AT (resolved from the conversation; lead with these):
{discussed}

VISIT TRANSCRIPT (may be short or empty):
{transcript}

SHORTLISTED PRODUCTS (recommend only from these):
{products}

Return ONLY valid JSON, no markdown, in this shape:
{{
  "recommendations": [
    {{
      "sku": "<one of the SKUs above>",
      "why": "1-2 sentences on why this mattress fits THIS customer, referencing their needs",
      "whatsapp_blurb": "1 short, friendly line to send on WhatsApp, including the no-cost EMI if relevant"
    }}
  ]
}}"""


def _fallback_why(product: dict) -> str:
    reasons = product.get("reasons") or []
    # Prefer substantive needs/benefit reasons over pure EMI/trial one-liners,
    # so even secondary picks explain why the product is worth considering.
    substantive = [
        r for r in reasons
        if not r.startswith("No-cost EMI") and not r.endswith("trial")
    ]
    if substantive:
        return " \u00b7 ".join(substantive[:2])
    positioning = product.get("positioning")
    if positioning:
        return positioning
    benefits = product.get("key_benefits") or []
    return benefits[0] if benefits else product.get("name", "")


def _fallback_blurb(product: dict) -> str:
    name = product.get("name", "this mattress")
    benefit = (product.get("key_benefits") or [None])[0] or product.get("positioning") or ""
    emi = product.get("emi") or emi_line(product)
    parts = [f"{name}"]
    if benefit:
        parts.append(benefit)
    line = " \u2014 ".join(parts)
    if emi:
        line += f". {emi}."
    return line


def _format_signals(signals: list[dict]) -> str:
    if not signals:
        return "(none detected)"
    seen: list[str] = []
    for s in signals[:12]:
        label = f"- {s.get('type', '')}/{s.get('subtype', '')}: {(s.get('quote') or '').strip()}".strip()
        if label not in seen:
            seen.append(label)
    return "\n".join(seen) or "(none detected)"


def _format_products_for_llm(products: list[dict]) -> str:
    lines = []
    for p in products:
        lines.append(
            f"- SKU {p.get('sku')}: {p.get('name')} | {p.get('firmness', '')} | "
            f"{p.get('technology', '')} | \u20b9{int(p.get('price_inr', 0)):,} "
            f"({emi_line(p)}) | ideal for: {', '.join(p.get('ideal_for') or [])} | "
            f"benefits: {', '.join(p.get('key_benefits') or [])}"
        )
    return "\n".join(lines)


def _parse_llm_json(raw: str | None) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty LLM response")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(raw)
        if match:
            return json.loads(match.group(0))
    raise ValueError("LLM response was not valid JSON")


def _format_discussed(products: list[dict], discussed_skus: list[str] | None) -> str:
    if not discussed_skus:
        return "(none clearly named)"
    names = {p.get("sku"): p.get("name") for p in products}
    lines = [f"- {sku}: {names.get(sku, sku)}" for sku in discussed_skus if sku]
    return "\n".join(lines) or "(none clearly named)"


def _ground_with_llm(products: list[dict], signals: list[dict],
                     transcript: str, llm_client, model: str,
                     discussed_skus: list[str] | None = None) -> dict[str, dict]:
    resp = llm_client.chat_completions(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _USER_TEMPLATE.format(
                signals=_format_signals(signals),
                discussed=_format_discussed(products, discussed_skus),
                transcript=(transcript or "(no transcript)")[:4000],
                products=_format_products_for_llm(products),
            )},
        ],
        model=model,
        max_tokens=1200,
        reasoning_effort="off",
    )
    from .providers.sarvam import SarvamClient
    parsed = _parse_llm_json(SarvamClient.message_text(resp))
    valid_skus = {p.get("sku") for p in products}
    out: dict[str, dict] = {}
    for rec in parsed.get("recommendations") or []:
        sku = rec.get("sku")
        if sku in valid_skus:
            out[sku] = {
                "why": str(rec.get("why") or "").strip(),
                "whatsapp_blurb": str(rec.get("whatsapp_blurb") or "").strip(),
            }
    return out


def recommend_products(catalog: dict, signals: list[dict], transcript: str = "",
                       llm_client=None, limit: int = 3,
                       model: str = "sarvam-30b",
                       discussed_skus: list[str] | None = None) -> list[dict]:
    """Return a grounded, ranked product shortlist for a visit.

    Each product carries: all catalog fields, ``match_score``, ``reasons``,
    ``emi``, ``why`` (LLM or deterministic), and ``whatsapp_blurb``.

    ``discussed_skus`` (most-discussed first, from voclyp/product_mentions.py)
    lead the shortlist so the mattress the customer actually looked at is shown
    first, ahead of purely needs-inferred picks.
    """
    shortlist = rank_products(catalog, signals or [], limit=limit,
                              discussed_skus=discussed_skus)
    if not shortlist:
        return []

    grounded: dict[str, dict] = {}
    if llm_client is not None:
        try:
            grounded = _ground_with_llm(shortlist, signals or [], transcript,
                                        llm_client, model, discussed_skus)
        except Exception:
            grounded = {}  # fail-soft: deterministic reasons still apply

    for p in shortlist:
        g = grounded.get(p.get("sku")) or {}
        p["why"] = g.get("why") or _fallback_why(p)
        p["whatsapp_blurb"] = g.get("whatsapp_blurb") or _fallback_blurb(p)
    return shortlist

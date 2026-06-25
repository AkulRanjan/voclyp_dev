"""Generate factual, product-grounded visit notes from the diarized transcript.

The summarizer reads the ORIGINAL spoken transcript (code-mixed Hindi/English) —
Sarvam-30b understands Hindi natively, so we never feed it the degraded English
translation. Output is a concise English business recap grounded strictly in the
tenant's product catalog (the 5 mattresses we actually sell), with crisp
"customer wants", real "objections", always-present coaching, and the specific
SKUs that came up. Every field has a deterministic, non-blank fallback so the
insight is useful even when the LLM is unavailable.
"""
from __future__ import annotations

import json
import re

from ..base import Stage
from ..registry import register
from ...catalog import emi_line, rank_products
from ...config import load_settings
from ...contracts import ConversationContext
from ...product_mentions import resolve_product_mentions
from ...providers.sarvam import SarvamClient
from .summarize import TaxonomySummarization

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}", re.MULTILINE)

_SYSTEM = (
    "You are a sales coach for The Sleep Company, a mattress retailer in India. "
    "You analyze a single store-visit conversation between a sales rep (agent) "
    "and a customer who spoke mostly in Hindi/Hinglish. "
    "Write ALL output in clear, concise English. Be specific and impactful — "
    "short phrases, no filler, no padding. "
    "You may ONLY reference products from the provided catalog; never invent "
    "products, prices, or customer details. If something was not discussed, omit it.\n"
    "CRITICAL accuracy rules:\n"
    "- Attribute correctly: 'customer_wants' must be what the CUSTOMER actually "
    "wanted. Do NOT list things the REP asked about or merely described. A rep "
    "question like 'do you have back pain?' answered 'no' means the customer has "
    "NO such need — never list it.\n"
    "- Respect negation: if the customer declines or denies something (e.g. "
    "'Non EMI', 'no back pain', 'not too soft'), do NOT list it as a want. "
    "'Non EMI' / 'one-time payment' means they DECLINED EMI.\n"
    "- 'objections' are hesitations or rejections by the CUSTOMER: price too "
    "high, declined EMI / wants to pay one-time, rejected a specific model, wants "
    "to think it over, comparing competitors. A firmness PREFERENCE (medium / not "
    "too soft / not too hard) is a want, NOT an objection. A feature the REP "
    "presented as a benefit (warranty, cooling) is NOT an objection. If there were "
    "no real objections, return an empty array.\n"
    "- Explored != wanted: a feature or product the customer looked at but did "
    "NOT choose (e.g. they were shown a cooling model but picked the non-cooling "
    "one) is NOT a customer_want. Only list what they actually wanted or chose.\n"
    "- If the customer chose a product, say so in visit_notes and put it first in "
    "products_discussed.\n"
    "- DO NOT HALLUCINATE. If no mattress was discussed, return an empty "
    "products_discussed. If the customer expressed no needs, return empty "
    "customer_wants. If no concerns were raised, return empty objections. If "
    "nothing was really sold or discussed (small talk, browsing, cut short), say "
    "that plainly in visit_notes and leave wants/objections/products empty — never "
    "invent a pitch or needs that did not happen."
)

_USER_TEMPLATE = """CONVERSATION (as spoken, Hindi/Hinglish):
{transcript}

DETECTED SIGNALS (may be empty):
{signals}

PRODUCTS REFERENCED IN THE CONVERSATION (resolved, most-discussed first; prefer these for products_discussed):
{discussed}

PRODUCT CATALOG — the only products you may mention (these 5 are what the rep sells):
{catalog}

Return ONLY a JSON object (no markdown) with these keys:
- "visit_notes": string. 2-3 plain-English sentences describing what actually
  happened: what the customer came in for, which mattress the rep pitched, and
  how it ended. Synthesize meaning — do NOT translate line by line.
- "customer_wants": array of <=3 SHORT phrases (3-6 words each) of what the
  customer actually cared about. Empty array if unclear.
- "objections": array of <=3 SHORT real concerns the customer raised (price,
  warranty/sagging, firmness, comparing brands). Empty array if none.
- "rep_did_well": array of <=2 short phrases. Empty if nothing notable.
- "coaching": array of EXACTLY 2-3 short, specific, actionable tips for next time.
  This must NEVER be empty.
- "products_discussed": array of objects {{"sku": <catalog sku>, "name":
  <catalog name>, "why": <<=12 word reason this fits the customer>}}. Only SKUs
  from the catalog above. Empty array if no specific product came up.
- "outcome": one of "promising", "neutral", "at_risk".

Return ONLY valid JSON."""


def _format_transcript(ctx: ConversationContext) -> str:
    """Original spoken text (not the English translation) for the LLM context."""
    lines = []
    for u in ctx.utterances:
        text = (u.text or u.normalized_text or "").strip()
        if not text:
            continue
        who = {"agent": "Sales rep", "customer": "Customer"}.get(u.speaker, u.speaker.title())
        lines.append(f"{who}: {text}")
    return "\n".join(lines) if lines else "(no speech detected)"


def _format_signals(ctx: ConversationContext) -> str:
    if not ctx.signals:
        return "(none)"
    return "\n".join(f"- {s.type}/{s.subtype}: {s.quote}" for s in ctx.signals[:12])


def _format_catalog(catalog: dict | None) -> str:
    products = (catalog or {}).get("products") or []
    if not products:
        return "(no catalog available)"
    lines = []
    for p in products:
        ideal = ", ".join(p.get("ideal_for") or []) or (p.get("positioning") or "")
        price = p.get("price_inr") or p.get("mrp_inr")
        price_str = f"\u20b9{int(price):,}" if price else "price n/a"
        emi = emi_line(p)
        lines.append(
            f"- {p.get('sku')}: {p.get('name')} ({price_str}; {emi or 'EMI n/a'}) "
            f"— for: {ideal}"
        )
    return "\n".join(lines)


def _signals_as_dicts(ctx: ConversationContext) -> list[dict]:
    return [
        {"type": s.type, "subtype": s.subtype, "quote": s.quote, "speaker": s.speaker}
        for s in ctx.signals
    ]


def _format_discussed(catalog: dict | None, discussed_skus: list[str]) -> str:
    if not discussed_skus:
        return "(no specific product clearly named)"
    names = {p.get("sku"): p.get("name") for p in (catalog or {}).get("products") or []}
    return "\n".join(f"- {sku}: {names.get(sku, sku)}" for sku in discussed_skus)


# Human-readable labels for the deterministic fallback, so wants/objections are
# crisp phrases rather than whole-utterance dumps.
_WANT_LABELS = {
    "orthopaedic_need": "Back & spine support",
    "cooling_need": "Cooling for hot sleepers",
    "firmness_preference": "Specific firmness feel",
    "trial_request": "Wants a home trial",
    "emi_request": "EMI / monthly payment option",
    "purchase_intent": "Ready to buy",
}
_OBJECTION_LABELS = {
    "budget_too_high": "Budget / price concern",
    "warranty_concern": "Warranty / sagging worry",
    "firmness_mismatch": "Firmness not right",
    "local_brand_sagging": "Bad experience with another brand",
    "competitor_brand": "Comparing with another brand",
}


# Signal types that indicate the visit had real sales substance (a need, an
# intent, an objection, a price reaction, a competitor mention, or a rep
# promise). If NONE of these fired and no product was named, there is nothing to
# summarise — so we stay honest instead of inventing needs/products/coaching.
_SUBSTANTIVE_TYPES = {
    "demand", "intent", "objection", "price_reaction",
    "competitor_mention", "promise",
}


def _sig_type(signal) -> str:
    return signal["type"] if isinstance(signal, dict) else signal.type


def _has_substance(ctx: ConversationContext, discussed: list[str] | None) -> bool:
    if discussed:
        return True
    return any(_sig_type(s) in _SUBSTANTIVE_TYPES for s in ctx.signals)


def _parse_llm_json(raw: str | None) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("LLM response was empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(raw)
        if match:
            return json.loads(match.group(0))
    raise ValueError("LLM response was not valid JSON")


def _clean_list(raw, limit: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _clean_products(raw, catalog: dict | None, limit: int = 3) -> list[dict]:
    valid_skus = {p.get("sku") for p in (catalog or {}).get("products") or []}
    names = {p.get("sku"): p.get("name") for p in (catalog or {}).get("products") or []}
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip()
        if sku not in valid_skus or sku in seen:
            continue  # ground strictly to the real catalog
        seen.add(sku)
        out.append({
            "sku": sku,
            "name": names.get(sku) or str(item.get("name") or "").strip(),
            "why": str(item.get("why") or "").strip()[:120],
        })
        if len(out) >= limit:
            break
    return out


class SarvamVisitNotes(Stage):
    name = "summarization"
    version = "sarvam-visit-notes-v2-grounded"

    def __init__(self, client: SarvamClient, taxonomy: dict,
                 catalog: dict | None = None, model: str = "sarvam-30b"):
        self.client = client
        self.model = model
        self.catalog = catalog
        self._taxonomy = TaxonomySummarization(taxonomy)

    def run(self, ctx: ConversationContext) -> None:
        self._taxonomy.run(ctx)

        # Which mattresses did the conversation actually reference (named once,
        # then "ye / isme / iska")? Most-discussed first.
        discussed = resolve_product_mentions(self.catalog, ctx.utterances)["ordered"]

        transcript = _format_transcript(ctx)
        if len(transcript) < 20 or transcript == "(no speech detected)":
            ctx.summary_text = (
                "The recording was too short or no clear speech was detected. "
                "Record the full visit with the phone near both speakers."
            )
            ctx.summary_fields["visit_notes"] = ctx.summary_text
            ctx.summary_fields["customer_wants"] = []
            ctx.summary_fields["objections"] = []
            ctx.summary_fields["rep_did_well"] = []
            ctx.summary_fields["coaching"] = [
                "Hold the phone between you and the customer for the whole visit.",
                "Open with discovery: ask about back pain, firmness, and budget.",
            ]
            ctx.summary_fields["products_discussed"] = []
            ctx.summary_fields["llm_outcome"] = "neutral"
            return

        try:
            resp = self.client.chat_completions(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": _USER_TEMPLATE.format(
                        transcript=transcript,
                        signals=_format_signals(ctx),
                        discussed=_format_discussed(self.catalog, discussed),
                        catalog=_format_catalog(self.catalog),
                    )},
                ],
                model=self.model,
                max_tokens=1200,
                temperature=0.0,
                reasoning_effort="off",
            )
            ctx.provider_usage["sarvam:chat-completions"] = (
                ctx.provider_usage.get("sarvam:chat-completions", 0) + 1
            )
            content = SarvamClient.message_text(resp)
            parsed = _parse_llm_json(content)
            self._apply(ctx, parsed, discussed)
        except Exception as exc:  # noqa: BLE001 - never sink the job on a flaky LLM
            # Fall back to a deterministic, product-grounded recap so every
            # section stays useful and coaching is never blank.
            self._apply_fallback(ctx, discussed)
            ctx.summary_fields["llm_error"] = str(exc)[:200]

    def _apply(self, ctx: ConversationContext, parsed: dict,
               discussed: list[str] | None = None) -> None:
        visit_notes = str(parsed.get("visit_notes") or "").strip()
        wants = _clean_list(parsed.get("customer_wants"), 3)
        objections = _clean_list(parsed.get("objections"), 3)
        rep_did_well = _clean_list(parsed.get("rep_did_well"), 2)
        coaching = _clean_list(parsed.get("coaching"), 3)
        products = _clean_products(parsed.get("products_discussed"), self.catalog)
        outcome = parsed.get("outcome") or "neutral"

        # No sale, no pitch, no needs? Stay honest — do not backfill invented
        # products/wants from the needs ranker. (A real catalog product named by
        # the LLM still counts as substance.)
        if not _has_substance(ctx, discussed) and not products:
            # Use the honest summary, not the model's — it may invent a pitch.
            empty = self._empty_insight(ctx)
            ctx.summary_text = empty["visit_notes"]
            ctx.summary_fields["visit_notes"] = ctx.summary_text
            ctx.summary_fields["customer_wants"] = []
            ctx.summary_fields["objections"] = []
            ctx.summary_fields["rep_did_well"] = rep_did_well[:2]
            ctx.summary_fields["coaching"] = (coaching or empty["coaching"])[:3]
            ctx.summary_fields["products_discussed"] = []
            # No sale/discussion → never "promising"; keep it neutral.
            ctx.summary_fields["llm_outcome"] = "neutral"
            return

        # Backfill anything the model left thin from the deterministic layer so
        # the insight is never blank.
        fb = self._fallback_fields(ctx, discussed)
        if not visit_notes:
            visit_notes = fb["visit_notes"]
        if not wants:
            wants = fb["customer_wants"]
        if not objections:
            objections = fb["objections"]
        if len(coaching) < 2:
            for tip in fb["coaching"]:
                if tip not in coaching:
                    coaching.append(tip)
                if len(coaching) >= 2:
                    break
        # Products actually referenced in the conversation win over inferred
        # ones; the deterministic resolver already ordered them most-discussed
        # first, so prefer that list when it exists.
        if discussed:
            products = fb["products_discussed"]
        elif not products:
            products = fb["products_discussed"]

        ctx.summary_text = visit_notes
        ctx.summary_fields["visit_notes"] = visit_notes
        ctx.summary_fields["customer_wants"] = wants
        ctx.summary_fields["objections"] = objections
        ctx.summary_fields["rep_did_well"] = rep_did_well
        ctx.summary_fields["coaching"] = coaching[:3]
        ctx.summary_fields["products_discussed"] = products
        ctx.summary_fields["llm_outcome"] = outcome

    def _apply_fallback(self, ctx: ConversationContext,
                        discussed: list[str] | None = None) -> None:
        fb = self._fallback_fields(ctx, discussed)
        ctx.summary_text = fb["visit_notes"]
        for key, val in fb.items():
            ctx.summary_fields[key] = val

    def _empty_insight(self, ctx: ConversationContext) -> dict:
        """Honest recap when nothing was sold/discussed — no invented pitch."""
        return {
            "visit_notes": (
                "No mattress was discussed in this visit and the customer did not "
                "share clear needs or buying signals, so there are no product "
                "insights to show yet."
            ),
            "customer_wants": [],
            "objections": [],
            "rep_did_well": [],
            "coaching": [
                "Open with discovery: ask about back/spine comfort, firmness "
                "preference, and budget.",
                "Walk the customer through at least one mattress and the no-cost "
                "EMI option.",
                "End with a clear next step: book a trial or send a WhatsApp quote.",
            ],
            "products_discussed": [],
            "llm_outcome": "neutral",
        }

    def _fallback_fields(self, ctx: ConversationContext,
                         discussed: list[str] | None = None) -> dict:
        """Deterministic, product-grounded recap from signals + catalog."""
        # Nothing substantive happened → stay honest, don't rank generic products.
        if not _has_substance(ctx, discussed):
            return self._empty_insight(ctx)
        sig_dicts = _signals_as_dicts(ctx)
        subtypes = [(s.get("subtype") or "") for s in sig_dicts]

        wants, seen = [], set()
        for st in subtypes:
            label = _WANT_LABELS.get(st)
            if label and label not in seen:
                wants.append(label)
                seen.add(label)

        objections, seen_o = [], set()
        for st in subtypes:
            label = _OBJECTION_LABELS.get(st)
            if label and label not in seen_o:
                objections.append(label)
                seen_o.add(label)

        # Seed products_discussed from what was actually referenced (resolved,
        # most-discussed first), then fill remaining slots from needs ranking.
        # Show up to 3 (a visit often covers 2-3 mattresses). When products were
        # actually named, only surface those; otherwise fall back to needs picks.
        limit = min(3, len(discussed)) if discussed else 2
        ranked = rank_products(self.catalog, sig_dicts, limit=max(limit, 2),
                               discussed_skus=discussed) if self.catalog else []
        products = [
            {
                "sku": p.get("sku"),
                "name": p.get("name"),
                "why": (p.get("reasons") or [p.get("positioning") or ""])[0],
            }
            for p in ranked
        ][:limit]

        n_turns = len(ctx.utterances)
        top = products[0]["name"] if products else None
        if top:
            pitched = f"The rep pitched the {top}."
        else:
            pitched = "No specific mattress was clearly pitched."
        wants_str = (", ".join(w.lower() for w in wants)) if wants else "general mattress needs"
        visit_notes = (
            f"A {n_turns}-turn visit covering {wants_str}. {pitched} "
            + ("Concerns were raised around " + ", ".join(o.lower() for o in objections) + "."
               if objections else "No major objections were raised.")
        )

        coaching = self._fallback_coaching(wants, objections, products)

        return {
            "visit_notes": visit_notes,
            "customer_wants": wants[:3],
            "objections": objections[:3],
            "rep_did_well": [],
            "coaching": coaching,
            "products_discussed": products,
            "llm_outcome": "neutral",
        }

    @staticmethod
    def _fallback_coaching(wants, objections, products) -> list[str]:
        tips: list[str] = []
        if not wants:
            tips.append("Ask discovery questions about pain points, firmness, and budget early.")
        if any("Budget" in o or "price" in o.lower() for o in objections):
            tips.append("Address budget by leading with no-cost EMI and the entry Smart Ortho.")
        if any("Warranty" in o or "sagging" in o.lower() for o in objections):
            tips.append("Counter sagging fears with the warranty and SmartGRID durability.")
        if products:
            tips.append(f"Lock in interest in the {products[0]['name']} with a trial + EMI offer.")
        tips.append("Close with a clear next step: book the trial or send a WhatsApp quote.")
        # Dedupe, guarantee at least 2.
        out: list[str] = []
        for t in tips:
            if t not in out:
                out.append(t)
        return out[:3] if len(out) >= 2 else (out + [
            "Recap the customer's needs and propose the best-fit mattress with EMI.",
        ])[:3]


@register("summarization", "sarvam_llm")
def _create(options, services):
    settings = services.get("settings") or load_settings()
    return SarvamVisitNotes(
        SarvamClient(settings.sarvam_api_key),
        services["taxonomy"],
        catalog=services.get("catalog"),
        model=options.get("model", "sarvam-30b"),
    )

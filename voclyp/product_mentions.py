"""Deterministic product-mention + anaphora resolution over a visit transcript.

In a real store conversation a customer/rep names a mattress once
("yeh ortho wala dekho") and then refers to it with pronouns ("ye", "isme",
"iska kya price", "wahi wala"). This module resolves those pronouns back to the
last-named product so the insight + recommendations reflect what was actually
discussed, not just inferred needs.

Fully offline and deterministic. The alias index is built from the catalog (an
editable per-product ``aliases`` list plus the product name and series/tech
tokens), so adding a spoken nickname is a data edit, not a code change.
"""
from __future__ import annotations

import re

# Demonstrative / anaphora cues in Hindi, Hinglish and English. When one of
# these appears WITHOUT a fresh product name, it refers back to the current
# product. Order longest-first so "this one" is tried before "this".
_ANAPHORA = [
    "this one", "that one", "same one", "wo wala", "woh wala", "yeh wala",
    "ye wala", "iss wala", "is wala", "ismein", "isme", "isko", "iska", "iski",
    "issi", "isi", "usko", "uska", "wahi", "yehi", "yeh", "yah", "this", "ye",
    "is", "us", "it",
]
_ANAPHORA_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in sorted(_ANAPHORA, key=len, reverse=True)) + r")\b"
)

# Generic series/tech tokens we DON'T want to treat as identifying a single SKU
# on their own ("mattress", "smartgrid" apply to all 5). Real disambiguation
# comes from the per-product aliases.
_GENERIC = {"smart", "smartgrid", "smart grid", "mattress", "gadda",
            "bed", "the sleep company", "sleep company"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def build_alias_index(catalog: dict) -> list[tuple[str, str]]:
    """Return [(alias, sku)] sorted longest-alias-first for greedy matching."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for p in (catalog or {}).get("products") or []:
        sku = p.get("sku")
        if not sku:
            continue
        candidates: list[str] = []
        candidates.extend(p.get("aliases") or [])
        # Distinguishing tokens from the name, minus generic words.
        name = _norm(p.get("name") or "")
        name = re.sub(r"\bmattress\b", "", name).strip()
        if name:
            candidates.append(name)
        for raw in candidates:
            alias = _norm(raw)
            if not alias or alias in _GENERIC:
                continue
            key = (alias, sku)
            if key not in seen:
                seen.add(key)
                pairs.append((alias, sku))
    # Longest alias first so "ortho pro" wins over "ortho", "snowtec" over "luxe".
    pairs.sort(key=lambda kv: len(kv[0]), reverse=True)
    return pairs


def _turn_text(turn) -> str:
    """Accept transcript dicts or Utterance-like objects; prefer ORIGINAL text."""
    if isinstance(turn, dict):
        return turn.get("text") or turn.get("normalized_text") or ""
    return getattr(turn, "text", "") or getattr(turn, "normalized_text", "") or ""


def _find_named(text: str, index: list[tuple[str, str]]) -> list[tuple[int, str]]:
    """Find product aliases in one line. Returns [(position, sku)] in order,
    greedily consuming matched spans so "ortho pro" isn't double-counted as
    "ortho"."""
    hits: list[tuple[int, str]] = []
    spans: list[tuple[int, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(not (e <= a or s >= b) for a, b in spans)

    for alias, sku in index:  # already longest-first
        for m in re.finditer(r"\b" + re.escape(alias) + r"\b", text):
            if not overlaps(m.start(), m.end()):
                spans.append((m.start(), m.end()))
                hits.append((m.start(), sku))
    hits.sort(key=lambda h: h[0])
    return hits


def resolve_product_mentions(catalog: dict, turns) -> dict:
    """Resolve product references (named + anaphora) across a transcript.

    ``turns`` is an ordered list of transcript dicts ({"text"/"normalized_text"})
    or Utterance-like objects. Returns::

        {
          "ordered": ["SMART-LUXE-SNOWTEC", ...],   # most-discussed first
          "dominant_sku": "SMART-LUXE-SNOWTEC" | None,
          "mentions": {sku: {"named": n, "anaphora": n, "total": n,
                              "first_turn": i, "last_turn": i}},
        }
    """
    index = build_alias_index(catalog)
    names = {p.get("sku"): p.get("name") for p in (catalog or {}).get("products") or []}
    stats: dict[str, dict] = {}
    current: str | None = None

    def bump(sku: str, turn: int, kind: str):
        s = stats.setdefault(
            sku, {"named": 0, "anaphora": 0, "total": 0,
                  "first_turn": turn, "last_turn": turn, "name": names.get(sku)}
        )
        s[kind] += 1
        s["total"] += 1
        s["last_turn"] = turn
        s["first_turn"] = min(s["first_turn"], turn)

    for i, turn in enumerate(turns or []):
        text = _norm(_turn_text(turn))
        if not text:
            continue

        named = _find_named(text, index)
        # Count every named SKU; the last-positioned one becomes the focus.
        for _, sku in named:
            bump(sku, i, "named")
        if named:
            current = named[-1][1]

        # Anaphora cues that are NOT part of a freshly-named product refer back
        # to the current focus. We only attribute one anaphora mention per turn
        # to avoid over-counting filler ("ye ye dekho").
        if current is not None and _ANAPHORA_RE.search(text):
            # If this turn named a product, the cue most likely points at it and
            # is already counted; only attribute anaphora when nothing was named.
            if not named:
                bump(current, i, "anaphora")

    ordered = sorted(
        stats.keys(),
        key=lambda sku: (stats[sku]["total"], stats[sku]["last_turn"]),
        reverse=True,
    )
    return {
        "ordered": ordered,
        "dominant_sku": ordered[0] if ordered else None,
        "mentions": stats,
    }

/** Turn a VoClyp insight document into sales-rep friendly sections. */

export type InsightSignal = {
  type: string;
  subtype?: string;
  speaker?: string;
  quote: string;
  turn?: number;
};

export type InsightTranscriptTurn = {
  turn: number;
  speaker: string;
  text: string;
  normalized_text?: string;
};

export type InsightScoring = {
  score?: number;
  rating?: string;
  outcome?: string;
  components?: {
    buying_intent?: number;
    commitment?: number;
    objection_pressure?: number;
    competitive_pressure?: number;
  };
};

export type ProductDiscussed = { sku: string; name: string; why?: string };

export type InsightView = {
  summary: string;
  visitNotes: string;
  score: number;
  rating: string;
  outcome: string;
  customerWants: string[];
  repDidWell: string[];
  objections: string[];
  improvements: string[];
  nextActions: string[];
  productsDiscussed: ProductDiscussed[];
  transcript: InsightTranscriptTurn[];
};

// Human labels so wants/objections are crisp phrases, never whole-utterance dumps.
const WANT_LABELS: Record<string, string> = {
  orthopaedic_need: 'Back & spine support',
  cooling_need: 'Cooling for hot sleepers',
  firmness_preference: 'Specific firmness feel',
  trial_request: 'Wants a home trial',
  emi_request: 'EMI / monthly payment option',
  purchase_intent: 'Ready to buy',
};
const OBJECTION_LABELS: Record<string, string> = {
  budget_too_high: 'Budget / price concern',
  warranty_concern: 'Warranty / sagging worry',
  firmness_mismatch: 'Firmness not right',
  local_brand_sagging: 'Bad experience with another brand',
  competitor_brand: 'Comparing with another brand',
};

function uniq(items: string[]): string[] {
  return items.filter((x, i) => x && items.indexOf(x) === i);
}

function asProducts(raw: unknown): ProductDiscussed[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((p) => p as Record<string, unknown>)
    .filter((p) => p && typeof p === 'object' && p.sku)
    .map((p) => ({ sku: String(p.sku), name: String(p.name || ''), why: String(p.why || '') }));
}

function asSignals(raw: unknown): InsightSignal[] {
  return Array.isArray(raw) ? (raw as InsightSignal[]) : [];
}

function asTranscript(raw: unknown): InsightTranscriptTurn[] {
  return Array.isArray(raw) ? (raw as InsightTranscriptTurn[]) : [];
}

function asScoring(raw: unknown): InsightScoring {
  return raw && typeof raw === 'object' ? (raw as InsightScoring) : {};
}

function asStringList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((x) => String(x)).filter(Boolean);
}

export function buildInsightView(insight: Record<string, unknown> | null | undefined): InsightView {
  const signals = asSignals(insight?.signals);
  const scoring = asScoring(insight?.scoring);
  const summaryObj = (insight?.summary as { text?: string; fields?: Record<string, unknown> }) || {};
  const fields = summaryObj.fields || {};

  const visitNotes = String(fields.visit_notes || summaryObj.text || '').trim();
  const llmWants = asStringList(fields.customer_wants);
  const llmObjections = asStringList(fields.objections);
  const llmCoaching = asStringList(fields.coaching);
  const repDidWell = asStringList(fields.rep_did_well);
  const productsDiscussed = asProducts(fields.products_discussed);

  // Prefer the LLM's crisp phrases; fall back to human subtype labels (never
  // whole-sentence signal quotes).
  const customerWants = llmWants.length
    ? llmWants.slice(0, 3)
    : uniq(
        signals
          .filter((s) => s.type === 'demand' || s.type === 'intent')
          .map((s) => WANT_LABELS[s.subtype || ''] || ''),
      ).slice(0, 3);

  // Objections are real concerns only — exclude price_reaction/emi_interest,
  // which signal interest, not an objection.
  const objections = llmObjections.length
    ? llmObjections.slice(0, 3)
    : uniq(
        signals
          .filter((s) => s.type === 'objection' || (s.type === 'competitor_mention'))
          .map((s) => OBJECTION_LABELS[s.subtype || ''] || ''),
      ).slice(0, 3);

  const score = typeof scoring.score === 'number' ? scoring.score : 50;
  const rating = scoring.rating || 'Average';
  const outcome = String(fields.llm_outcome || scoring.outcome || 'neutral');

  // "How you could improve" must never be blank.
  let improvements = llmCoaching.length
    ? llmCoaching.slice(0, 3)
    : buildHeuristicCoaching(signals, score, customerWants.length, objections, productsDiscussed);
  if (improvements.length < 1) {
    improvements = ['Recap the customer\u2019s needs and propose the best-fit mattress with EMI.'];
  }

  const nextActions = buildNextActions(signals, fields);

  return {
    summary: visitNotes || summaryObj.text || '',
    visitNotes,
    score,
    rating,
    outcome,
    customerWants,
    repDidWell,
    objections,
    improvements,
    nextActions,
    productsDiscussed,
    transcript: asTranscript(insight?.transcript),
  };
}

function buildHeuristicCoaching(
  signals: InsightSignal[],
  score: number,
  wants: number,
  objections: string[],
  products: ProductDiscussed[],
): string[] {
  const tips: string[] = [];
  if (!wants) tips.push('Ask discovery questions about pain points, firmness, and budget early.');
  if (objections.some((o) => /budget|price/i.test(o))) {
    tips.push('Address budget by leading with no-cost EMI and the entry Smart Ortho.');
  }
  if (objections.some((o) => /warranty|sagging/i.test(o)) || signals.some((s) => s.type === 'competitor_mention')) {
    tips.push('Counter sagging fears with the warranty and SmartGRID durability.');
  }
  if (products.length) {
    tips.push(`Lock in interest in the ${products[0].name} with a trial + EMI offer.`);
  }
  if (score < 45) tips.push('Use a clearer structure: needs → product → trial/EMI → close.');
  tips.push('Close with a clear next step: book the trial or send a WhatsApp quote.');
  return uniq(tips).slice(0, 3);
}

function buildNextActions(signals: InsightSignal[], fields: Record<string, unknown>): string[] {
  const actions: string[] = [];
  if (fields.buying_readiness) actions.push('Customer showed purchase intent — send quote and book delivery.');
  if (signals.some((s) => s.subtype === 'trial_request' || s.subtype === 'emi_request')) {
    actions.push('Offer 100-night trial and no-cost EMI.');
  }
  if (!actions.length) actions.push('Follow up on WhatsApp with a personalised recommendation.');
  return actions;
}

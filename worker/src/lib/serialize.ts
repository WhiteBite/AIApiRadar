// Helper: parse JSON fields
export function parseJson(val: unknown): unknown {
  if (typeof val !== 'string') return val
  try { return JSON.parse(val) } catch { return val }
}

export function offerToDict(offer: Record<string, unknown>, domain: string | null) {
  return {
    id: offer.id,
    service_id: offer.service_id,
    domain,
    name: (offer.name as string | null) || (domain ?? offer.url),
    type: offer.type,
    amount: offer.amount,
    currency: offer.currency,
    models: parseJson(offer.models) || [],
    claim_steps: offer.claim_steps,
    requirements: offer.requirements,
    conditions: parseJson(offer.conditions) || {},
    referral_required: Boolean(offer.referral_required),
    effort: offer.effort,
    unit: offer.unit,
    description: offer.description,
    url: offer.url,
    score: Math.round(((offer.score as number) || 0) * 10000) / 10000,
    status: offer.service_status || offer.status,
    reliability: offer.reliability,
    engine: offer.engine,
    domain_first_seen: offer.domain_first_seen,
    first_seen_at: offer.first_seen_at,
    source: offer.source ?? null,
    source_url: offer.source_url ?? null,
    likes: Number(offer.likes ?? 0),
    dislikes: Number(offer.dislikes ?? 0),
  }
}

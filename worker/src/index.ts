import { Hono } from 'hono'
import { cors } from 'hono/cors'

type Env = {
  DB: D1Database
}

const app = new Hono<{ Bindings: Env }>()

// CORS for the Next.js frontend (Cloudflare Pages)
app.use('*', cors({
  origin: ['https://aiapiradar.cf.whitebite.ru', 'https://aiapiradar.pages.dev', 'http://localhost:3000'],
  allowMethods: ['GET'],
}))

// Helper: parse JSON fields
function parseJson(val: unknown): unknown {
  if (typeof val !== 'string') return val
  try { return JSON.parse(val) } catch { return val }
}

function offerToDict(offer: Record<string, unknown>, domain: string | null) {
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
  }
}

// GET /api/offers
app.get('/api/offers', async (c) => {
  const { type, min_amount, model, status, q, sort, since_hours, limit = '100', offset = '0' } = c.req.query()

  let sql = `
    SELECT o.*, s.canonical_domain, s.name as service_name,
           s.status as service_status, s.reliability, s.engine,
           s.domain_first_seen
    FROM offers o
    LEFT JOIN services s ON o.service_id = s.id
    WHERE 1=1
  `
  const params: (string | number)[] = []

  if (type) { sql += ' AND o.type = ?'; params.push(type) }
  if (min_amount) { sql += ' AND o.amount >= ?'; params.push(Number(min_amount)) }
  if (status) { sql += ' AND s.status = ?'; params.push(status) }
  if (q) {
    sql += ' AND (LOWER(s.canonical_domain) LIKE ? OR LOWER(COALESCE(s.name,"")) LIKE ?)'
    params.push(`%${q.toLowerCase()}%`, `%${q.toLowerCase()}%`)
  }
  // Freshness window: only offers first seen within the last N hours.
  if (since_hours) {
    const h = Math.max(1, Math.min(Number(since_hours) || 0, 24 * 365))
    sql += " AND o.first_seen_at >= datetime('now', ?)"
    params.push(`-${h} hours`)
  }

  // Sorting. Default 'score' is recency-dominant (see scorer). 'new' = pure
  // recency, 'amount' = biggest bonus first.
  if (sort === 'new') {
    sql += ' ORDER BY o.first_seen_at DESC, o.score DESC'
  } else if (sort === 'amount') {
    sql += ' ORDER BY o.amount DESC, o.score DESC'
  } else {
    sql += ' ORDER BY o.score DESC, o.first_seen_at DESC'
  }
  sql += ` LIMIT ? OFFSET ?`
  params.push(Number(limit), Number(offset))

  const result = await c.env.DB.prepare(sql).bind(...params).all()
  let items = (result.results as Record<string, unknown>[]).map(row =>
    offerToDict(row, row.canonical_domain as string | null)
  )

  // Post-filter by model (JSON field search)
  if (model) {
    const m = model.toLowerCase()
    items = items.filter(it =>
      Array.isArray(it.models) && it.models.some((x: unknown) =>
        String(x).toLowerCase().includes(m)
      )
    )
  }

  return c.json({ count: items.length, items })
})

// GET /api/services/:id
app.get('/api/services/:id', async (c) => {
  const id = Number(c.req.param('id'))
  if (!id) return c.json({ error: 'invalid id' }, 400)

  const svc = await c.env.DB.prepare(
    'SELECT * FROM services WHERE id = ?'
  ).bind(id).first()

  if (!svc) return c.json({ error: 'not found' }, 404)

  const offersRes = await c.env.DB.prepare(
    'SELECT * FROM offers WHERE service_id = ?'
  ).bind(id).all()

  const signalsRes = await c.env.DB.prepare(
    'SELECT source, source_url, observed_at FROM signals WHERE service_id = ? ORDER BY observed_at DESC LIMIT 20'
  ).bind(id).all()

  return c.json({
    id: svc.id,
    domain: svc.canonical_domain,
    name: svc.name,
    type: svc.type,
    engine: svc.engine,
    status: svc.status,
    reliability: svc.reliability,
    domain_first_seen: svc.domain_first_seen,
    offers: (offersRes.results as Record<string, unknown>[]).map(o =>
      offerToDict(o, svc.canonical_domain as string)
    ),
    signals: signalsRes.results,
  })
})

// GET /api/stats
app.get('/api/stats', async (c) => {
  const [services, active, dead, offers, byType] = await Promise.all([
    c.env.DB.prepare('SELECT COUNT(*) as n FROM services').first<{ n: number }>(),
    c.env.DB.prepare("SELECT COUNT(*) as n FROM services WHERE status='active'").first<{ n: number }>(),
    c.env.DB.prepare("SELECT COUNT(*) as n FROM services WHERE status='dead'").first<{ n: number }>(),
    c.env.DB.prepare('SELECT COUNT(*) as n FROM offers').first<{ n: number }>(),
    c.env.DB.prepare('SELECT type, COUNT(*) as n FROM offers GROUP BY type').all(),
  ])

  const by_type: Record<string, number> = {}
  for (const row of byType.results as { type: string; n: number }[]) {
    by_type[row.type] = row.n
  }

  return c.json({
    services: services?.n ?? 0,
    active: active?.n ?? 0,
    dead: dead?.n ?? 0,
    offers: offers?.n ?? 0,
    by_type,
  })
})

export default app

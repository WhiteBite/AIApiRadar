import { Hono } from 'hono'
import type { Env } from '../types'
import { offerToDict } from '../lib/serialize'

export const offers = new Hono<{ Bindings: Env }>()

// GET /api/offers
offers.get('/api/offers', async (c) => {
  const { type, min_amount, model, status, q, sort, since_hours, limit = '100', offset = '0' } = c.req.query()

  let sql = `
    SELECT o.*, s.canonical_domain, s.name as service_name,
           s.status as service_status, s.reliability, s.engine,
           s.domain_first_seen,
           (SELECT source FROM signals WHERE offer_id = o.id ORDER BY observed_at ASC LIMIT 1) as source,
           (SELECT source_url FROM signals WHERE offer_id = o.id ORDER BY observed_at ASC LIMIT 1) as source_url,
           COALESCE(v.likes, 0) as likes,
           COALESCE(v.dislikes, 0) as dislikes
    FROM offers o
    LEFT JOIN services s ON o.service_id = s.id
    LEFT JOIN (
      SELECT offer_id,
             SUM(CASE WHEN vote=1 THEN 1 ELSE 0 END) as likes,
             SUM(CASE WHEN vote=-1 THEN 1 ELSE 0 END) as dislikes
      FROM votes GROUP BY offer_id
    ) v ON v.offer_id = o.id
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

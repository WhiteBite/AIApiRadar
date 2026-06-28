import { Hono } from 'hono'
import type { Env } from '../types'
import { offerToDict } from '../lib/serialize'

export const services = new Hono<{ Bindings: Env }>()

// GET /api/services/:id
services.get('/api/services/:id', async (c) => {
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
    'SELECT source, source_url, observed_at, raw_text FROM signals WHERE service_id = ? ORDER BY observed_at DESC LIMIT 20'
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

import { Hono } from 'hono'
import type { Env } from '../types'
import { COLLECTOR_META, STREAM_COLLECTORS } from '../_generated'

export const collectors = new Hono<{ Bindings: Env }>()

// ── Collector metadata ──────────────────────────────────────────────────────
// COLLECTOR_META + STREAM_COLLECTORS are generated from the canonical Python
// sources (see ./_generated and scripts/gen_worker_constants.py).

// GET /api/collectors — live registry with enabled status from sources table
collectors.get('/api/collectors', async (c) => {
  const rows = await c.env.DB.prepare(
    'SELECT name, enabled FROM sources WHERE type != ?'
  ).bind('telegram').all<{ name: string; enabled: number }>()

  const enabledMap = new Map(
    (rows.results ?? []).map(r => [r.name, r.enabled !== 0])
  )

  const result = Object.entries(COLLECTOR_META)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, meta]) => ({
      name,
      label: meta.label,
      dot: meta.dot,
      kind: 'api',
      mode: STREAM_COLLECTORS.has(name) ? 'stream' : 'poll',
      interval: 900,
      enabled: enabledMap.has(name) ? enabledMap.get(name)! : true,
      requires: meta.requires,
      // Worker can't check Python env vars — key_present is unknown
      key_present: null as boolean | null,
    }))

  return c.json(result)
})

// PATCH /api/collectors/:name — toggle enabled / set interval
collectors.patch('/api/collectors/:name', async (c) => {
  const name = c.req.param('name')
  if (!(name in COLLECTOR_META)) return c.json({ error: 'not found' }, 404)

  const body = await c.req.json<{ enabled?: boolean; interval?: number }>()

  // Upsert into sources table
  const existing = await c.env.DB.prepare(
    'SELECT id, config FROM sources WHERE name = ?'
  ).bind(name).first<{ id: number; config: string | null }>()

  if (existing) {
    const sets: string[] = []
    const params: (string | number)[] = []
    if (body.enabled !== undefined) { sets.push('enabled = ?'); params.push(body.enabled ? 1 : 0) }
    if (body.interval !== undefined) {
      let cfg: Record<string, unknown> = {}
      try { cfg = JSON.parse(existing.config ?? '{}') } catch { /* ignore */ }
      cfg.interval = body.interval
      sets.push('config = ?'); params.push(JSON.stringify(cfg))
    }
    if (sets.length) {
      params.push(existing.id)
      await c.env.DB.prepare(
        `UPDATE sources SET ${sets.join(', ')} WHERE id = ?`
      ).bind(...params).run()
    }
  } else {
    const cfg = body.interval ? JSON.stringify({ interval: body.interval }) : '{}'
    await c.env.DB.prepare(
      'INSERT INTO sources (name, type, enabled, config) VALUES (?, ?, ?, ?)'
    ).bind(name, 'collector', body.enabled !== false ? 1 : 0, cfg).run()
  }

  return c.json({ ok: true })
})

// GET /api/keys — which env keys are needed and by whom
// Note: Worker can't see Python env vars, so present:false for all.
// The frontend shows these as "configure in .env / GitHub Secrets".
collectors.get('/api/keys', async (c) => {
  const keyMap = new Map<string, string[]>()
  for (const [name, meta] of Object.entries(COLLECTOR_META)) {
    if (meta.requires) {
      const list = keyMap.get(meta.requires) ?? []
      list.push(name)
      keyMap.set(meta.requires, list)
    }
  }
  const result = [...keyMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, unlocks]) => ({ key, present: false, unlocks }))
  return c.json(result)
})

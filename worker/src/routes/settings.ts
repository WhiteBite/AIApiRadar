import { Hono } from 'hono'
import type { Env } from '../types'
import { SETTINGS_DEFAULTS } from '../_generated'

export const settings = new Hono<{ Bindings: Env }>()

// ── App settings ──────────────────────────────────────────────────────────────
// SETTINGS_DEFAULTS is generated from the canonical Python sources
// (prefilter.py + scorer.py + config.py Settings) — see ./_generated.

// GET /api/settings — returns settings merged with defaults
settings.get('/api/settings', async (c) => {
  const rows = await c.env.DB.prepare('SELECT key, value FROM app_settings').all<{ key: string; value: string }>()
  const stored: Record<string, unknown> = {}
  for (const r of rows.results ?? []) {
    try { stored[r.key] = JSON.parse(r.value) } catch { stored[r.key] = r.value }
  }
  return c.json({ ...SETTINGS_DEFAULTS, ...stored })
})

// PATCH /api/settings — upsert one or more known keys
settings.patch('/api/settings', async (c) => {
  const body = await c.req.json<Record<string, unknown>>()
  const now = new Date().toISOString()
  for (const [key, value] of Object.entries(body)) {
    if (!(key in SETTINGS_DEFAULTS)) continue  // only allow known keys
    await c.env.DB.prepare(
      'INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)'
    ).bind(key, JSON.stringify(value), now).run()
  }
  return c.json({ ok: true })
})

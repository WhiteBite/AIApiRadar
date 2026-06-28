import { Hono } from 'hono'
import type { Env } from '../types'

export const stats = new Hono<{ Bindings: Env }>()

// GET /api/stats
stats.get('/api/stats', async (c) => {
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

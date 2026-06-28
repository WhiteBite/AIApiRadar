// Smoke tests for the Cloudflare Worker API (Hono 4 + D1).
// We invoke routes in-process via `app.request(path, init, { DB })`, where DB
// is an in-memory better-sqlite3 database exposing the D1 surface. No network.
import { describe, it, expect, beforeEach } from 'vitest'
import app from '../src/index'
import { makeTestDB } from './d1'

let DB: any

beforeEach(() => {
  DB = makeTestDB()
})

// Helper: call a GET route against the seeded DB.
async function get(path: string) {
  return app.request(path, undefined, { DB })
}

describe('GET /api/version', () => {
  it('returns version + build_date', async () => {
    const res = await get('/api/version')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('version')
    expect(body).toHaveProperty('build_date')
  })
})

describe('GET /api/offers', () => {
  it('returns { count, items } with offer shape incl. conditions/likes/dislikes/source', async () => {
    const res = await get('/api/offers')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('count')
    expect(Array.isArray(body.items)).toBe(true)
    expect(body.count).toBeGreaterThan(0)
    expect(body.count).toBe(body.items.length)

    const item = body.items[0]
    for (const key of ['id', 'domain', 'conditions', 'likes', 'dislikes', 'source']) {
      expect(item).toHaveProperty(key)
    }
    // Top offer (score 0.85) is offer 1: example-ai.com, earliest signal = producthunt,
    // one like + one dislike, conditions parsed to an object.
    expect(item.id).toBe(1)
    expect(item.domain).toBe('example-ai.com')
    expect(item.source).toBe('producthunt')
    expect(item.likes).toBe(1)
    expect(item.dislikes).toBe(1)
    expect(item.conditions).toEqual({ min_topup: 5, region: 'global' })
  })
})

describe('GET /api/stats', () => {
  it('returns services/active/dead/offers/by_type', async () => {
    const res = await get('/api/stats')
    expect(res.status).toBe(200)
    const body = await res.json()
    for (const key of ['services', 'active', 'dead', 'offers', 'by_type']) {
      expect(body).toHaveProperty(key)
    }
    expect(body.services).toBe(2)
    expect(body.active).toBe(1)
    expect(body.dead).toBe(1)
    expect(body.offers).toBe(2)
    expect(body.by_type).toMatchObject({ free_credit: 1, trial: 1 })
  })
})

describe('GET /api/analytics', () => {
  it('returns lead_time / by_source / source_leaderboard', async () => {
    const res = await get('/api/analytics')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('lead_time')
    expect(body).toHaveProperty('by_source')
    expect(body).toHaveProperty('source_leaderboard')
    expect(body.lead_time).toHaveProperty('count_total')
    expect(Array.isArray(body.by_source)).toBe(true)
    expect(Array.isArray(body.source_leaderboard)).toBe(true)
    expect(body.lead_time.count_total).toBe(2)
  })
})

describe('GET /api/collectors', () => {
  it('returns the known collector registry (>= 26 entries incl. appstore + certstream)', async () => {
    const res = await get('/api/collectors')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body)).toBe(true)
    expect(body.length).toBeGreaterThanOrEqual(26)
    const names = body.map((x: any) => x.name)
    expect(names).toContain('appstore')
    expect(names).toContain('certstream')
    // enabled flag reflects the sources table seed.
    const appstore = body.find((x: any) => x.name === 'appstore')
    expect(appstore.enabled).toBe(true)
    const twitter = body.find((x: any) => x.name === 'twitter')
    expect(twitter.enabled).toBe(false)
  })
})

describe('GET /api/settings', () => {
  it('returns defaults merged with stored overrides', async () => {
    const res = await get('/api/settings')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('prefilter_en_strong')
    expect(body).toHaveProperty('score_w_freshness')
    // stored override wins over the generated default.
    expect(body.notify_min_score).toBe(0.7)
  })
})

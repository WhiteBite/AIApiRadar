// Test-only D1 adapter backed by an in-memory better-sqlite3 database.
// Exposes the subset of the D1Database surface the worker uses:
//   prepare(sql) -> { bind(...args), all(), first(col?), run() }
// This lets us call the Hono app via `app.request(path, init, { DB })`
// with no network and fully deterministic data.
import Database from 'better-sqlite3'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

class FakePreparedStatement {
  constructor(db, sql, params) {
    this.db = db
    this.sql = sql
    this.params = params || []
  }

  bind(...args) {
    return new FakePreparedStatement(this.db, this.sql, args)
  }

  async all() {
    const stmt = this.db.prepare(this.sql)
    const results = stmt.all(...this.params)
    return { results, success: true, meta: {} }
  }

  async first(col) {
    const stmt = this.db.prepare(this.sql)
    const row = stmt.get(...this.params)
    if (row === undefined || row === null) return null
    if (col !== undefined) return row[col]
    return row
  }

  async run() {
    const stmt = this.db.prepare(this.sql)
    const info = stmt.run(...this.params)
    return {
      success: true,
      meta: { changes: info.changes, last_row_id: Number(info.lastInsertRowid) },
    }
  }
}

class FakeD1 {
  constructor(db) {
    this.db = db
  }
  prepare(sql) {
    return new FakePreparedStatement(this.db, sql, [])
  }
}

// Build a seeded in-memory DB. Returns a FakeD1 usable as `env.DB`.
export function makeTestDB() {
  const db = new Database(':memory:')

  // Canonical schema (services/offers/signals/sources/lead_metrics/votes/...).
  const schemaPath = resolve(__dirname, '../../aiapiradar/db/schema.sql')
  db.exec(readFileSync(schemaPath, 'utf8'))

  // app_settings lives outside schema.sql — it is created in deploy.yml.
  db.exec(
    "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT DEFAULT (datetime('now')));"
  )

  seed(db)
  return new FakeD1(db)
}

function seed(db) {
  // ── services ──────────────────────────────────────────────────────────────
  const insService = db.prepare(
    `INSERT INTO services (id, canonical_domain, name, type, engine, status, reliability, domain_first_seen)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  )
  insService.run(1, 'example-ai.com', 'Example AI', 'llm', 'gpt', 'active', 0.9, '2024-01-01T00:00:00')
  insService.run(2, 'dead-ai.com', 'Dead AI', 'image', null, 'dead', 0.1, '2024-02-01T00:00:00')

  // ── offers ──────────────────────────────────────────────────────────────
  const insOffer = db.prepare(
    `INSERT INTO offers (id, service_id, type, amount, currency, models, claim_steps, requirements,
                         conditions, referral_required, effort, unit, description, url, status, score, first_seen_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  )
  insOffer.run(
    1, 1, 'free_credit', 10, 'usd', '["gpt-4","claude-3"]', 'Sign up with email', 'email',
    '{"min_topup": 5, "region": "global"}', 0, 'easy', 'usd', 'Free credits on signup',
    'https://example-ai.com/free', 'active', 0.85, '2024-06-01T12:00:00'
  )
  insOffer.run(
    2, 2, 'trial', 5, 'usd', '["sdxl"]', 'Register', 'phone',
    '{}', 1, 'medium', 'days', 'Trial period', 'https://dead-ai.com/trial',
    'dead', 0.40, '2024-05-01T12:00:00'
  )

  // ── signals (two for offer 1 to exercise earliest-source subquery) ─────────
  const insSignal = db.prepare(
    `INSERT INTO signals (offer_id, service_id, source, source_url, observed_at)
     VALUES (?, ?, ?, ?, ?)`
  )
  insSignal.run(1, 1, 'producthunt', 'https://producthunt.com/p/example-ai', '2024-06-01T10:00:00')
  insSignal.run(1, 1, 'reddit', 'https://reddit.com/r/x/abc', '2024-06-01T11:00:00')
  insSignal.run(2, 2, 'github', 'https://github.com/x/y', '2024-05-01T09:00:00')

  // ── votes (one like, one dislike on offer 1) ──────────────────────────────
  const insVote = db.prepare(
    `INSERT INTO votes (offer_id, fingerprint, vote) VALUES (?, ?, ?)`
  )
  insVote.run(1, 'fingerprint-aaa', 1)
  insVote.run(1, 'fingerprint-bbb', -1)

  // ── lead_metrics ──────────────────────────────────────────────────────────
  const insLead = db.prepare(
    `INSERT INTO lead_metrics (offer_id, lead_hours) VALUES (?, ?)`
  )
  insLead.run(1, 5.0)
  insLead.run(2, 2.0)

  // ── sources (drives enabled flags on /api/collectors) ─────────────────────
  const insSource = db.prepare(
    `INSERT INTO sources (name, type, enabled, config) VALUES (?, ?, ?, ?)`
  )
  insSource.run('appstore', 'collector', 1, '{}')
  insSource.run('twitter', 'collector', 0, '{}')

  // ── app_settings (one stored override) ─────────────────────────────────────
  db.prepare(
    `INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)`
  ).run('notify_min_score', '0.7', '2024-06-01T12:00:00')
}

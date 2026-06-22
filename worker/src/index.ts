import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { VERSION, BUILD_DATE } from './_version'

type Env = {
  DB: D1Database
}

const app = new Hono<{ Bindings: Env }>()

// CORS for the Next.js frontend (Cloudflare Pages)
app.use('*', cors({
  origin: ['https://aiapiradar.cf.whitebite.ru', 'https://aiapiradar.pages.dev', 'http://localhost:3000'],
  allowMethods: ['GET', 'PATCH', 'POST'],
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
    source: offer.source ?? null,
    source_url: offer.source_url ?? null,
    likes: Number(offer.likes ?? 0),
    dislikes: Number(offer.dislikes ?? 0),
  }
}

// ── Fingerprint helper ────────────────────────────────────────────────────────
// SHA-256 of CF-Connecting-IP + User-Agent — identifies a visitor without storing PII.
async function fingerprint(req: Request): Promise<string> {
  const ip = req.headers.get('CF-Connecting-IP')
    ?? req.headers.get('X-Forwarded-For')?.split(',')[0]?.trim()
    ?? 'unknown';
  const ua = req.headers.get('User-Agent') ?? 'unknown';
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${ip}|${ua}`));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}

// GET /api/offers
app.get('/api/offers', async (c) => {
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

// GET /api/analytics
app.get('/api/analytics', async (c) => {
  const [leadRows, bySourceRows, descCount, totalCount] = await Promise.all([
    c.env.DB.prepare(
      'SELECT lead_hours FROM lead_metrics WHERE lead_hours IS NOT NULL ORDER BY lead_hours'
    ).all<{ lead_hours: number }>(),
    c.env.DB.prepare(
      'SELECT source, COUNT(*) as cnt FROM signals GROUP BY source ORDER BY cnt DESC LIMIT 10'
    ).all<{ source: string; cnt: number }>(),
    c.env.DB.prepare(
      'SELECT COUNT(*) as c FROM offers WHERE description IS NOT NULL'
    ).first<{ c: number }>(),
    c.env.DB.prepare(
      'SELECT COUNT(*) as c FROM offers'
    ).first<{ c: number }>(),
  ])

  const leadValues = (leadRows.results as { lead_hours: number }[]).map(r => r.lead_hours)
  // Already sorted ASC by SQL
  const count_total = leadValues.length
  const aheadValues = leadValues.filter(v => v > 0)
  const count_ahead = aheadValues.length

  let avg_hours: number | null = null
  let median_hours: number | null = null

  if (aheadValues.length > 0) {
    avg_hours = Math.round(
      (aheadValues.reduce((a, b) => a + b, 0) / aheadValues.length) * 100
    ) / 100
  }

  if (count_total > 0) {
    const mid = Math.floor(count_total / 2)
    median_hours = count_total % 2 === 0
      ? (leadValues[mid - 1] + leadValues[mid]) / 2
      : leadValues[mid]
  }

  const by_source = (bySourceRows.results as { source: string; cnt: number }[]).map(r => ({
    source: r.source,
    count: r.cnt,
  }))

  return c.json({
    lead_time: {
      avg_hours,
      median_hours,
      count_ahead,
      count_total,
    },
    by_source,
    with_description: descCount?.c ?? 0,
    offers_total: totalCount?.c ?? 0,
  })
})

// ── Collector metadata (mirrors _COLLECTOR_META in web.py) ──────────────────
const COLLECTOR_META: Record<string, { label: string; dot: string; requires: string | null }> = {
  certstream: { label: 'CertStream (CT-логи)', dot: 'cyan', requires: null },
  crtsh: { label: 'crt.sh (новые домены)', dot: 'cyan', requires: null },
  forum_rss: { label: 'Форумы (nodeseek / linux.do / RSSHub)', dot: 'orange', requires: null },
  hackernews: { label: 'Hacker News', dot: 'orange', requires: null },
  reddit: { label: 'Reddit', dot: 'orange', requires: null },
  github: { label: 'GitHub', dot: 'zinc', requires: 'AIRADAR_GITHUB_TOKEN' },
  github_lists: { label: 'GitHub awesome-lists', dot: 'zinc', requires: 'AIRADAR_GITHUB_TOKEN' },
  huggingface: { label: 'HuggingFace (релизы моделей)', dot: 'yellow', requires: null },
  producthunt: { label: 'Product Hunt', dot: 'red', requires: null },
  directories: { label: 'AI-каталоги (BetaList/Uneed…)', dot: 'lime', requires: null },
  coupon: { label: 'Агрегаторы сделок (AppSumo…)', dot: 'purple', requires: null },
  youtube: { label: 'YouTube', dot: 'red', requires: 'AIRADAR_YOUTUBE_API_KEY' },
  searchdorks: { label: 'Search dorks (Google CSE)', dot: 'blue', requires: 'AIRADAR_SEARCH_API_KEY' },
  twitter: { label: 'Twitter / X', dot: 'sky', requires: 'AIRADAR_TW_BEARER_TOKEN' },
  telegram: { label: 'Telegram ingest', dot: 'sky', requires: 'AIRADAR_TG_API_ID' },
  openrouter: { label: 'OpenRouter (каталог моделей)', dot: 'violet', requires: null },
  packages: { label: 'npm / PyPI (AI SDK пакеты)', dot: 'zinc', requires: null },
  fofa: { label: 'FOFA (favicon-hash сканер)', dot: 'red', requires: 'AIRADAR_FOFA_KEY' },
  leaks: { label: 'Gists / Pastebin (утечки)', dot: 'zinc', requires: 'AIRADAR_GITHUB_TOKEN' },
}

const STREAM_COLLECTORS = new Set(['certstream', 'telegram'])

// GET /api/collectors — live registry with enabled status from sources table
app.get('/api/collectors', async (c) => {
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
app.patch('/api/collectors/:name', async (c) => {
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
app.get('/api/keys', async (c) => {
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

// ── Voting endpoints ──────────────────────────────────────────────────────────

// POST /api/offers/:id/vote  { vote: 1 | -1 | 0 }   (0 = remove vote)
app.post('/api/offers/:id/vote', async (c) => {
  const offerId = Number(c.req.param('id'))
  if (!offerId) return c.json({ error: 'invalid id' }, 400)

  const body = await c.req.json<{ vote: number }>().catch(() => ({ vote: 0 }))
  const vote = Number(body.vote)
  if (![1, -1, 0].includes(vote)) return c.json({ error: 'vote must be 1, -1 or 0' }, 400)

  const fp = await fingerprint(c.req.raw)

  if (vote === 0) {
    await c.env.DB.prepare(
      'DELETE FROM votes WHERE offer_id=? AND fingerprint=?'
    ).bind(offerId, fp).run()
  } else {
    await c.env.DB.prepare(
      'INSERT OR REPLACE INTO votes (offer_id, fingerprint, vote, created_at) VALUES (?, ?, ?, datetime("now"))'
    ).bind(offerId, fp, vote).run()
  }

  const counts = await c.env.DB.prepare(
    `SELECT SUM(CASE WHEN vote=1  THEN 1 ELSE 0 END) as likes,
            SUM(CASE WHEN vote=-1 THEN 1 ELSE 0 END) as dislikes
     FROM votes WHERE offer_id=?`
  ).bind(offerId).first<{ likes: number; dislikes: number }>()

  return c.json({ likes: counts?.likes ?? 0, dislikes: counts?.dislikes ?? 0, my_vote: vote })
})

// GET /api/offers/:id/my-vote  — returns this visitor's vote for the offer
app.get('/api/offers/:id/my-vote', async (c) => {
  const offerId = Number(c.req.param('id'))
  if (!offerId) return c.json({ error: 'invalid id' }, 400)

  const fp = await fingerprint(c.req.raw)
  const row = await c.env.DB.prepare(
    'SELECT vote FROM votes WHERE offer_id=? AND fingerprint=?'
  ).bind(offerId, fp).first<{ vote: number }>()

  return c.json({ my_vote: row?.vote ?? 0 })
})

// GET /api/version — deployed commit SHA and build date
app.get('/api/version', (c) => c.json({ version: VERSION, build_date: BUILD_DATE }))

// ── App settings ──────────────────────────────────────────────────────────────
// Default values mirror prefilter.py and scorer.py constants.
const SETTINGS_DEFAULTS = {
  prefilter_en_strong: [
    "free credit", "free credits", "free trial", "free api", "free tier", "api trial",
    "no credit card", "no card required", "sign up free", "register for free", "free access",
    "free tokens", "free quota", "get free", "claim free", "free plan includes",
    "promo code", "coupon code", "discount code", "use code", "free pro", "pro for free", "pro plan free",
    "get it free", "access for free", "free with",
  ],
  prefilter_en_weak: ["credits", "sign up", "signup", "register", "redeem", "promo", "referral", "invite", "api key", "trial", "$"],
  prefilter_ru: ["триал", "кредит", "бесплатн", "api ключ", "апи ключ", "регистрац", "раздач", "раздают", "баланс", "халяв", "промокод", "бонус"],
  prefilter_zh_strong: ["注册送", "公益站", "中转站", "免费api", "白嫖", "送额度", "送余额", "送刀", "免费额度", "注册即送", "新用户送"],
  prefilter_zh_weak: ["免费", "额度", "中转"],
  score_w_freshness: 0.4,
  score_w_amount: 0.3,
  score_w_ease: 0.2,
  score_w_reliability: 0.1,
  early_signal_boost: 0.1,
  discovery_limit: 40,
  notify_min_score: 0.6,
} as const

// GET /api/settings — returns settings merged with defaults
app.get('/api/settings', async (c) => {
  const rows = await c.env.DB.prepare('SELECT key, value FROM app_settings').all<{ key: string; value: string }>()
  const stored: Record<string, unknown> = {}
  for (const r of rows.results ?? []) {
    try { stored[r.key] = JSON.parse(r.value) } catch { stored[r.key] = r.value }
  }
  return c.json({ ...SETTINGS_DEFAULTS, ...stored })
})

// PATCH /api/settings — upsert one or more known keys
app.patch('/api/settings', async (c) => {
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

export default app

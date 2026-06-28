import { Hono } from 'hono'
import type { Env } from '../types'

export const analytics = new Hono<{ Bindings: Env }>()

// GET /api/analytics
analytics.get('/api/analytics', async (c) => {
  const [leadRows, bySourceRows, descCount, totalCount, leaderboardRows] = await Promise.all([
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
    // Source-attribution scoreboard: which FIRST source (earliest signal)
    // gives offers the biggest lead over Telegram aggregators.
    c.env.DB.prepare(`
      SELECT first_src AS source,
             ROUND(AVG(lead_hours), 2) AS avg_lead,
             COUNT(*) AS total,
             SUM(CASE WHEN lead_hours > 0 THEN 1 ELSE 0 END) AS ahead
      FROM (
        SELECT lm.lead_hours AS lead_hours,
               (SELECT source FROM signals WHERE offer_id = lm.offer_id ORDER BY observed_at ASC LIMIT 1) AS first_src
        FROM lead_metrics lm
        WHERE lm.lead_hours IS NOT NULL
      )
      WHERE first_src IS NOT NULL
      GROUP BY first_src
      ORDER BY avg_lead DESC
    `).all<{ source: string; avg_lead: number; total: number; ahead: number }>(),
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

  const source_leaderboard = (leaderboardRows.results as { source: string; avg_lead: number; total: number; ahead: number }[]).map(r => ({
    source: r.source,
    avg_lead_hours: r.avg_lead,
    count_total: r.total,
    count_ahead: r.ahead,
  }))

  return c.json({
    lead_time: {
      avg_hours,
      median_hours,
      count_ahead,
      count_total,
    },
    by_source,
    source_leaderboard,
    with_description: descCount?.c ?? 0,
    offers_total: totalCount?.c ?? 0,
  })
})

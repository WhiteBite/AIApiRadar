import { Hono } from 'hono'
import type { Env } from '../types'
import { fingerprint } from '../lib/fingerprint'

export const votes = new Hono<{ Bindings: Env }>()

// ── Voting endpoints ──────────────────────────────────────────────────────────

// POST /api/offers/:id/vote  { vote: 1 | -1 | 0 }   (0 = remove vote)
votes.post('/api/offers/:id/vote', async (c) => {
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
votes.get('/api/offers/:id/my-vote', async (c) => {
  const offerId = Number(c.req.param('id'))
  if (!offerId) return c.json({ error: 'invalid id' }, 400)

  const fp = await fingerprint(c.req.raw)
  const row = await c.env.DB.prepare(
    'SELECT vote FROM votes WHERE offer_id=? AND fingerprint=?'
  ).bind(offerId, fp).first<{ vote: number }>()

  return c.json({ my_vote: row?.vote ?? 0 })
})

import { Hono } from 'hono'
import { cors } from 'hono/cors'
import type { Env } from './types'
import { offers } from './routes/offers'
import { votes } from './routes/votes'
import { services } from './routes/services'
import { stats } from './routes/stats'
import { analytics } from './routes/analytics'
import { collectors } from './routes/collectors'
import { settings } from './routes/settings'
import { version } from './routes/version'

const app = new Hono<{ Bindings: Env }>()

// CORS for the Next.js frontend (Cloudflare Pages)
app.use('*', cors({
  origin: ['https://aiapiradar.cf.whitebite.ru', 'https://aiapiradar.pages.dev', 'http://localhost:3000'],
  allowMethods: ['GET', 'PATCH', 'POST'],
}))

// Sub-apps keep their full `/api/...` paths, so mounting at '/' preserves them exactly.
app.route('/', offers)
app.route('/', votes)
app.route('/', services)
app.route('/', stats)
app.route('/', analytics)
app.route('/', collectors)
app.route('/', settings)
app.route('/', version)

export default app

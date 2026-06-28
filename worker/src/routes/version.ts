import { Hono } from 'hono'
import type { Env } from '../types'
import { VERSION, BUILD_DATE } from '../_version'

export const version = new Hono<{ Bindings: Env }>()

// GET /api/version — deployed commit SHA and build date
version.get('/api/version', (c) => c.json({ version: VERSION, build_date: BUILD_DATE }))

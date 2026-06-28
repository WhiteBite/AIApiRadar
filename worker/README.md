# AiApiRadar — Cloudflare Worker

## Deploy

1. Create D1 database:
   ```bash
   wrangler d1 create aiapiradar
   ```
   Copy the `database_id` into `wrangler.toml`.

2. Initialize schema (`schema.sql` is auto-generated from `db/base.py` —
   regenerate with `python -m scripts.gen_schema`, never edit it by hand):
   ```bash
   wrangler d1 execute aiapiradar --file=../aiapiradar/db/schema.sql
   ```

3. Install and deploy:
   ```bash
   npm install
   npm run deploy
   ```

## GitHub Actions (collectors)

Add the repo secrets listed in `docs/discovery-sources.md` §13 (token registry).
At minimum:
- `CF_ACCOUNT_ID`
- `CF_D1_DATABASE_ID`
- `CF_API_TOKEN`

All collector / LLM keys (`AIRADAR_*`) are optional — each source degrades to a
graceful no-op (or the heuristic classifier) without its key.

The collectors run every hour via `.github/workflows/collectors.yml`.

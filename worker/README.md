# AiApiRadar — Cloudflare Worker

## Deploy

1. Create D1 database:
   ```bash
   wrangler d1 create aiapiradar
   ```
   Copy the `database_id` into `wrangler.toml`.

2. Initialize schema:
   ```bash
   wrangler d1 execute aiapiradar --file=../aiapiradar/db/schema.sql
   ```

3. Install and deploy:
   ```bash
   npm install
   npm run deploy
   ```

## GitHub Actions (collectors)

Add these secrets to your GitHub repo:
- `CF_ACCOUNT_ID`
- `CF_D1_DATABASE_ID`
- `CF_API_TOKEN`
- `LLM_API_KEY` (optional)
- `TG_BOT_TOKEN` / `TG_CHAT_ID` (optional)

The collectors run every hour via `.github/workflows/collectors.yml`.

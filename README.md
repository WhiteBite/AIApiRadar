# AiApiRadar

Multi-source monitor that finds **free AI API credit / trial offers** as early
as possible — ideally before they reach aggregator Telegram channels.

The core insight: different kinds of deals first surface in different places, so
no single source wins. AiApiRadar watches the **union** of sources, classifies
and de-duplicates them into a ranked feed, and measures how far ahead of the
Telegram ecosystem it actually is.

## How it works

```
collectors ─▶ normalize ─▶ pre-filter ─▶ classify ─▶ enrich ─▶ dedup/store ─▶ score ─▶ API/UI + notify
```

- **Collectors** (one plugin per source) emit raw `Signal`s.
- **Pre-filter** drops obvious noise (RU/EN/CN keywords) before the LLM.
- **Classifier** (LLM when an API key is set, else a heuristic fallback)
  extracts `service_name, offer_type, amount, models, claim_steps, …`.
- **Enrich** probes the service (alive? `/pricing`? relay engine? domain age via
  crt.sh) and computes a reliability score.
- **Store** keeps `Service ⟵ Offer ⟵ Signal`, de-duplicated.
- **Score** ranks offers by `freshness × amount × ease × reliability`.
- **Lead metric** records first-seen-by-us vs first-seen-in-aggregator so you can
  verify the head start.

### Sources

| collector   | what it catches                                  |
|-------------|--------------------------------------------------|
| certstream  | brand-new relay domains (CT logs, realtime)      |
| forum_rss   | nodeseek / linux.do / v2ex (Chinese relays)      |
| directories | theresanaiforthat / futurepedia / toolify        |
| github      | repos/gists advertising free credits             |
| huggingface | new model releases from key orgs                 |
| producthunt | new SaaS launches                                |
| searchdorks | Google Programmable Search dorks (opt-in)        |
| coupon      | coupon/affiliate sites (established-SaaS promos)  |
| telegram    | upstream channels (the "tail"; aggregator)       |
| youtube     | recent videos about credits/giveaways (opt-in)   |

## Setup

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in any keys you have (all optional)
```

All API keys are optional — collectors that need a missing key simply skip.
Without an LLM key the heuristic classifier is used.

## Usage (CLI)

```bash
python -m aiapiradar.cli init-db        # create tables
python -m aiapiradar.cli collectors     # list registered collectors
python -m aiapiradar.cli run            # start the scheduler (collect loop)
python -m aiapiradar.cli enrich         # probe/enrich stale services
python -m aiapiradar.cli score          # recompute offer scores
python -m aiapiradar.cli notify         # push fresh high-score offers to Telegram
python -m aiapiradar.cli serve          # web dashboard + API at :8000
```

Installed as a package (`pip install -e .`), the same commands are available as
`aiapiradar <command>`.

## Docker

```bash
cp .env.example .env
docker compose up --build
# dashboard: http://localhost:8000
```

`scheduler` runs the collectors/watchdog/notifier; `web` serves the dashboard.
Both share a SQLite volume; switch to Postgres via the commented block in
`docker-compose.yml` for concurrent access.

## Configuration (env, `AIRADAR_` prefix)

| key | purpose |
|-----|---------|
| `AIRADAR_DB_URL` | SQLite (default) or Postgres URL |
| `AIRADAR_LLM_API_KEY` / `_BASE_URL` / `_MODEL` | enable LLM classifier (OpenAI-compatible) |
| `AIRADAR_TG_BOT_TOKEN` / `_CHAT_ID` / `NOTIFY_MIN_SCORE` | Telegram notifications |
| `AIRADAR_GITHUB_TOKEN` | higher GitHub rate limits |
| `AIRADAR_SEARCH_API_KEY` / `_CX` | Google Programmable Search |
| `AIRADAR_YOUTUBE_API_KEY` | YouTube Data API |
| `AIRADAR_TG_API_ID` / `_API_HASH` / `_SESSION` | Telethon channel ingest |
| `AIRADAR_SCORE_W_*` | scoring weights |

## Tests

```bash
python -m pytest -q
```

## Notes

- The schema is created with `create_all` (no migrations yet). After model
  changes in dev, delete the SQLite file to recreate.
- Telegram ingest needs an interactive first login to create the session file.
- Treat external/relay services with caution: many are short-lived and some
  proxy via dubious backends. Don't send them sensitive data.

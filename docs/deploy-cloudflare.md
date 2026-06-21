# Deploying on Cloudflare — operator checklist

Short, factual checklist for running AiApiRadar with Cloudflare D1 as the data
store. Read alongside `docs/architecture.md` §1 and §5.

> **Reality check (architecture §1).** The Python pipeline (httpx / feedparser /
> bs4 / websocket) does **not** run natively on Cloudflare Workers. On the
> Cloudflare topology, "cloudflare" means **data in D1 + a static frontend**.
> The pipeline runs in CI or a container and writes to D1 over the REST API.
> Cloudflare itself hosts D1 (storage), the read-API Worker, and the Pages
> frontend — not the collectors.

---

## 1. Required environment

All settings use the `AIRADAR_` prefix (`config.py`). To point the Python
pipeline at D1:

| Env var | Purpose |
|---|---|
| `AIRADAR_PLATFORM=cloudflare` | Selects the D1 backend; `runtime.setup()` registers `d1_db_factory`. |
| `AIRADAR_CF_ACCOUNT_ID` | Cloudflare account id (D1 REST URL). |
| `AIRADAR_CF_D1_DATABASE_ID` | Target D1 database id. |
| `AIRADAR_CF_API_TOKEN` | API token with D1 read/write. |
| `AIRADAR_RUNNER=batch` | One-shot pass, no APScheduler (serverless / cron model). With `auto`, `cloudflare` already resolves to `batch`. |

Budget vars (serverless tuning — see §5):

| Env var | Purpose |
|---|---|
| `AIRADAR_MAX_SUBREQUESTS` | Cap on outbound subrequests per run. `0` = unlimited (VDS); set `>0` on Cloudflare. |
| `AIRADAR_DISCOVERY_LIMIT` | Max domain candidates probed per discovery run (default `40`). |

`AIRADAR_PLATFORM=cloudflare` makes both `Database` (D1) and the runner derive
correctly: `runtime.setup()` → `d1_db_factory`, and `sched.get_runner()` →
`batch` when `AIRADAR_RUNNER=auto`.

---

## 2. One-time D1 initialization

`init_db()` creates the tables/indexes one statement at a time (D1-safe) and
applies the incremental `ALTER TABLE` migrations. Run it once against D1 with
the Cloudflare env set. The CLI exposes an `init-db` command (`cli.py`):

```bash
# with the AIRADAR_CF_* + AIRADAR_PLATFORM=cloudflare env exported
AIRADAR_PLATFORM=cloudflare \
AIRADAR_CF_ACCOUNT_ID=... \
AIRADAR_CF_D1_DATABASE_ID=... \
AIRADAR_CF_API_TOKEN=... \
python -m aiapiradar.cli init-db
```

Equivalent explicit form (same effect, no CLI):

```bash
python -c "from aiapiradar.runtime import setup; from aiapiradar.db.base import init_db; setup(); init_db()"
```

Both route through `get_db()`, so with `AIRADAR_PLATFORM=cloudflare` the DDL is
issued over the D1 REST API. `init_db()` is idempotent — re-running it on an
up-to-date schema is safe.

---

## 3. Triggering the batch runner

The batch runner (`sched/batch_runner.py`, via `run_batch_sync`) runs **one**
pass: every enabled `poll` collector once → pipeline → enrich/watchdog →
discovery → notify, then exits. It is invoked by `python -m aiapiradar.cli
collect-once` (`cmd_collect_once`).

Two practical trigger options:

- **GitHub Actions (current hybrid — recommended).** `.github/workflows/collectors.yml`
  runs hourly (`cron: '0 * * * *'`). It runs the whole pipeline against a local
  SQLite (`AIRADAR_PLATFORM=local`), then syncs to D1 at the boundaries with
  `wrangler d1 export` (pull) and `wrangler d1 execute --file` (push, via
  `cli.py dump-sql`). This is the proven path and needs no Python-on-D1.
- **CF Cron Worker → batch entrypoint.** A Cloudflare Cron Worker cannot run the
  Python pipeline; it can only trigger an external container/CI job that runs
  `collect-once` with `AIRADAR_PLATFORM=cloudflare` (writing directly to D1 over
  REST). Use this only if you run the pipeline in a container rather than CI.

The separate `.github/workflows/deploy.yml` deploys the read-API Worker and the
Pages frontend — it does **not** run collectors.

---

## 4. Streaming caveat

The `certstream` collector is `mode = "stream"` (`collectors/certstream.py`): a
long-lived websocket with in-memory buffers that only survive on a VDS. The
batch runner deliberately **skips** stream collectors (counted as
`collectors_skipped_stream`), so certstream does **not** run on Cloudflare/CI.
Domain discovery there is covered by `crtsh` (the `poll` equivalent that polls
crt.sh statelessly for new `%.ai/%.io/%.app/%.dev` certs) — see architecture
§3.3.

---

## 5. Budget tuning (subrequest caps)

Cloudflare imposes a subrequest cap per invocation (50 free / 1000 paid;
architecture §1). The pipeline honours `RunBudget` (`core/budget.py`), built
from settings via `RunBudget.from_settings()` inside `run_batch`:

- `AIRADAR_MAX_SUBREQUESTS` — keep below the platform cap (e.g. ~45 on free
  tier) to leave headroom. `0` disables the cap (VDS only).
- `AIRADAR_DISCOVERY_LIMIT` — fewer probes per run = fewer subrequests; lower it
  if discovery dominates the budget.
- `collect-once --limit N` trims how many collectors run in a single pass — a
  crude additional cap when a full pass is too heavy for one invocation.

Start conservative, watch the `budget` block in the `run_batch` stats, and raise
limits once a live run stays under the cap.

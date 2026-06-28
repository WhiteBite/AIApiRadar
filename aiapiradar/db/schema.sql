-- AUTO-GENERATED from aiapiradar/db/base.py (SCHEMA_SQL).
-- Do not edit by hand — regenerate with:  python -m scripts.gen_schema

CREATE TABLE IF NOT EXISTS services (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_domain  TEXT    NOT NULL UNIQUE,
    name              TEXT,
    type              TEXT    NOT NULL DEFAULT 'other',
    engine            TEXT,
    models            TEXT,           -- JSON array
    aliases           TEXT,           -- JSON array of all hosts seen
    status            TEXT    NOT NULL DEFAULT 'new',
    reliability       REAL    NOT NULL DEFAULT 0.0,
    domain_first_seen TEXT,           -- ISO datetime
    first_seen        TEXT    NOT NULL DEFAULT (datetime('now')),
    last_checked      TEXT
);

CREATE TABLE IF NOT EXISTS offers (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id        INTEGER NOT NULL REFERENCES services(id),
    type              TEXT    NOT NULL DEFAULT 'other',
    amount            REAL,
    currency          TEXT,
    models            TEXT,           -- JSON array
    claim_steps       TEXT,
    requirements      TEXT,
    conditions        TEXT,           -- JSON object (structured offer conditions)
    referral_required INTEGER NOT NULL DEFAULT 0,
    effort            TEXT,           -- easy / medium / hard
    unit              TEXT,           -- usd / credits / days / months
    topic             TEXT,           -- ai_service / freebie (telegram notify routing)
    description       TEXT,           -- short blurb parsed from the service page
    url               TEXT,
    status            TEXT    NOT NULL DEFAULT 'new',
    score             REAL    NOT NULL DEFAULT 0.0,
    notified_at       TEXT,
    first_seen_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    last_verified_at  TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id       INTEGER REFERENCES offers(id),
    service_id     INTEGER REFERENCES services(id),
    source         TEXT    NOT NULL,
    source_url     TEXT,
    url            TEXT,
    raw_text       TEXT,
    lang           TEXT,
    classification TEXT,              -- JSON object
    confidence     REAL,
    observed_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_url)
);

CREATE TABLE IF NOT EXISTS sources (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT    NOT NULL UNIQUE,
    type     TEXT    NOT NULL,
    enabled  INTEGER NOT NULL DEFAULT 1,
    last_run TEXT,
    config   TEXT                     -- JSON object
);

CREATE TABLE IF NOT EXISTS lead_metrics (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id                 INTEGER NOT NULL UNIQUE REFERENCES offers(id),
    first_seen_by_us         TEXT,
    first_seen_in_aggregator TEXT,
    lead_hours               REAL
);

CREATE TABLE IF NOT EXISTS domain_candidates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    domain        TEXT    NOT NULL UNIQUE,   -- registrable domain (eTLD+1)
    first_source  TEXT,                       -- collector that first mentioned it
    first_seen    TEXT    NOT NULL DEFAULT (datetime('now')),
    probed_at     TEXT,
    status        TEXT    NOT NULL DEFAULT 'pending',  -- pending/promoted/rejected/known
    probe_result  TEXT,                       -- JSON summary of the probe
    attempts      INTEGER NOT NULL DEFAULT 0,
    priority      TEXT    NOT NULL DEFAULT 'normal'  -- normal / high (offer trigger nearby)
);

CREATE INDEX IF NOT EXISTS idx_domain_candidates_status_attempts
    ON domain_candidates (status, attempts, first_seen);

CREATE INDEX IF NOT EXISTS idx_domain_candidates_domain
    ON domain_candidates (domain);

CREATE INDEX IF NOT EXISTS idx_signals_source_source_url
    ON signals (source, source_url);

-- Votes: per-offer like/dislike, one vote per fingerprint (SHA-256 of IP+UA).
CREATE TABLE IF NOT EXISTS votes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id    INTEGER NOT NULL REFERENCES offers(id),
  fingerprint TEXT    NOT NULL,
  vote        INTEGER NOT NULL,  -- +1 like, -1 dislike
  created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE(offer_id, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_votes_offer ON votes(offer_id);

CREATE TABLE IF NOT EXISTS services (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_domain  TEXT    NOT NULL UNIQUE,
    name              TEXT,
    type              TEXT    NOT NULL DEFAULT 'other',
    engine            TEXT,
    models            TEXT,
    status            TEXT    NOT NULL DEFAULT 'new',
    reliability       REAL    NOT NULL DEFAULT 0.0,
    domain_first_seen TEXT,
    first_seen        TEXT    NOT NULL DEFAULT (datetime('now')),
    last_checked      TEXT
);

CREATE TABLE IF NOT EXISTS offers (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id        INTEGER NOT NULL REFERENCES services(id),
    type              TEXT    NOT NULL DEFAULT 'other',
    amount            REAL,
    currency          TEXT,
    models            TEXT,
    claim_steps       TEXT,
    requirements      TEXT,
    referral_required INTEGER NOT NULL DEFAULT 0,
    effort            TEXT,           -- easy / medium / hard
    unit              TEXT,           -- usd / credits / days / months
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
    classification TEXT,
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
    config   TEXT
);

CREATE TABLE IF NOT EXISTS lead_metrics (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id                 INTEGER NOT NULL UNIQUE REFERENCES offers(id),
    first_seen_by_us         TEXT,
    first_seen_in_aggregator TEXT,
    lead_hours               REAL
);

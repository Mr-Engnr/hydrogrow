-- HydroGrow expo SQLite schema. Applied idempotently by ingest.py on start
-- and by the backend (both open the same file, WAL mode).

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- One row per telemetry message, mirroring one blob per message in Azure.
-- raw_json is the payload exactly as received from the Pi (timestamp intact).
-- blob_name reproduces the Azure name YYYYMMDD_HHMMSS_microseconds.json so
-- "latest" selection in the backend is identical to the old regex + max().
CREATE TABLE IF NOT EXISTS telemetry (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    blob_name          TEXT    NOT NULL UNIQUE,
    ingested_at        TEXT    NOT NULL,          -- naive UTC ISO, what processTelemetry wrote as "timestamp"
    ingest_day         TEXT    NOT NULL,          -- YYYY-MM-DD from blob_name, analytics bucket key
    pi_timestamp       TEXT,                      -- Pi's own tz-aware timestamp from the payload
    source             TEXT    NOT NULL DEFAULT 'pi',   -- 'pi' | 'fake' | 'replay'
    ph                 REAL,                      -- normalised from "pH" or "ph"
    ec                 REAL,
    tds                REAL,
    temperature        REAL,
    humidity           REAL,
    water_level        REAL,                      -- raw cm distance, as sent
    water_level_cm     REAL,
    water_level_pct    REAL,
    water_low          INTEGER,                   -- 0/1/NULL
    growth_day_actual  INTEGER,
    growth_day_model   INTEGER,
    growth_phase       TEXT,
    harvest_flush      INTEGER,
    status             TEXT,
    image              TEXT,
    nutrient_label     TEXT,
    nutrient_confidence REAL,                     -- 0-100 as sent
    plant1_label       TEXT,
    plant1_confidence  REAL,                      -- 0-1 as sent
    plant2_label       TEXT,
    plant2_confidence  REAL,
    plant3_label       TEXT,
    plant3_confidence  REAL,
    dosing_a_dosed     INTEGER,
    dosing_b_dosed     INTEGER,
    raw_json           TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_blob_name ON telemetry(blob_name);
CREATE INDEX IF NOT EXISTS idx_telemetry_ingest_day ON telemetry(ingest_day);

-- Digital-twin replacement. One row per (twin, property), same property names
-- processTelemetry wrote with JSON-Patch. value_json keeps the JSON type so
-- the /twins/:id endpoint returns numbers as numbers and booleans as booleans.
CREATE TABLE IF NOT EXISTS twin_state (
    twin_id    TEXT NOT NULL,
    property   TEXT NOT NULL,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (twin_id, property)
);

-- Twin identity, mirrors $dtId / $metadata.$model in ADT. Seeded by ingest.
CREATE TABLE IF NOT EXISTS twins (
    twin_id  TEXT PRIMARY KEY,
    model_id TEXT NOT NULL
);
INSERT OR IGNORE INTO twins (twin_id, model_id) VALUES
    ('plant1',       'dtmi:hydroponic:plant;2'),
    ('plant2',       'dtmi:hydroponic:plant;2'),
    ('plant3',       'dtmi:hydroponic:plant;2'),
    ('watertank1',   'dtmi:hydroponic:watertank;1'),
    ('environment1', 'dtmi:hydroponic:environment;1');

-- Users, replacing backend/src/data/users.json. Same fields as the JSON record.
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE,
    password   TEXT NOT NULL,     -- bcrypt hash
    name       TEXT NOT NULL,
    token      TEXT,              -- opaque bearer token, NULL when logged out
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_token ON users(token);

-- Liveness for /health. Each service upserts its own row.
CREATE TABLE IF NOT EXISTS service_state (
    service    TEXT PRIMARY KEY,  -- 'ingest'
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

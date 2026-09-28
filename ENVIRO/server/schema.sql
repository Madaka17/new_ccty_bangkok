-- ENVIRO Seismic Command -- database schema
-- SQLite. Applied once on first run (see server/db.py).

CREATE TABLE IF NOT EXISTS users (
  username      TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL,           -- admin | operator | auditor | partner
  display_name  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       TEXT NOT NULL,
  username TEXT NOT NULL,
  action   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stations (
  id           TEXT PRIMARY KEY,
  region       TEXT NOT NULL,
  lat          REAL NOT NULL,
  lng          REAL NOT NULL,
  status       TEXT NOT NULL DEFAULT 'online',
  installed_at TEXT NOT NULL
);

-- Aggregate counts for the wider nationwide fleet (only the rows in `stations`
-- above are individually simulated with real waveform buffers; this table
-- represents the administrative fleet-management view of the full network).
CREATE TABLE IF NOT EXISTS station_regions (
  region TEXT PRIMARY KEY,
  total  INTEGER NOT NULL,
  online INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fault_lines (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  name   TEXT NOT NULL,
  region TEXT NOT NULL,
  lat1 REAL, lng1 REAL, lat2 REAL, lng2 REAL
);

-- 6-level alert ladder, gated on PREDICTED MMI AT THE REFERENCE LOCATION
-- ("you are here" -- currently the BKK-201 station), not on epicenter
-- magnitude directly. This follows the same real-world reasoning USGS gives
-- for why Magnitude != Intensity: one event produces very different shaking
-- at different places depending on distance, depth, path, and site
-- conditions, so the *level a specific viewer sees* has to be intensity-based,
-- not a single global magnitude threshold. See references in db.py.
CREATE TABLE IF NOT EXISTS levels (
  lv          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  mmi_min     REAL NOT NULL,        -- primary gate: predicted MMI (numeric, I=1..XII=12) at the reference location
  mmi_max     REAL,                 -- NULL = no upper bound (level 6)
  mmi_roman   TEXT NOT NULL,        -- display label, e.g. "VII–VIII"
  severity_desc TEXT NOT NULL,      -- comparative severity description (what it feels/looks like)
  mag_ref     TEXT NOT NULL,        -- typical/reference originating magnitude range -- informational only, not a gate
  pga_min     REAL NOT NULL,        -- reference PGA band for display only, not the classification gate
  pga_max     REAL,
  ai_conf     TEXT NOT NULL,
  nodes_min   TEXT NOT NULL,        -- multi-node corroboration -> confidence tier, not a level cap
  message     TEXT NOT NULL,
  channels    TEXT NOT NULL,
  siren       TEXT NOT NULL,
  color       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id                 TEXT PRIMARY KEY,
  ts                 TEXT NOT NULL,
  magnitude          REAL NOT NULL,
  depth              REAL NOT NULL,
  place              TEXT NOT NULL,
  fault              TEXT NOT NULL,
  lat REAL, lng REAL,
  mmi_epicenter      TEXT NOT NULL,
  predicted_mmi      REAL NOT NULL DEFAULT 0,   -- numeric MMI (I=1..XII=12) at the reference "you are here" location -- the level gate
  tsunami_risk       INTEGER NOT NULL DEFAULT 0, -- see Simulator._assess_tsunami_risk: a documented, simplified heuristic, not an official warning
  stations_triggered INTEGER NOT NULL,
  level              INTEGER NOT NULL,
  pga_gal            REAL NOT NULL,
  is_test            INTEGER NOT NULL DEFAULT 0,
  speed_multiplier   REAL NOT NULL DEFAULT 1.0
);

-- Real earthquake events from external feeds (USGS/EMSC/GEOFON/TMD),
-- persisted permanently as they're first discovered. This is distinct from
-- server/world_quakes.py's in-memory cache, which only ever holds whatever
-- the most recent poll returned and is lost on every restart -- this table
-- instead accumulates genuine history over the system's actual running
-- lifetime, growing past any single external API's own retention/query
-- window (USGS/GEOFON's global feed here only goes back 90 days; this table
-- keeps everything ever seen). It's the raw material for future Edge AI
-- trend analysis and forecasting -- this table itself does no analysis.
CREATE TABLE IF NOT EXISTS world_quake_history (
  id            TEXT PRIMARY KEY,   -- source-prefixed real event id, e.g. "usgs-us7000abcd" -- natural de-dup key
  source        TEXT NOT NULL,      -- USGS | EMSC | GEOFON | TMD
  lat           REAL NOT NULL,
  lng           REAL NOT NULL,
  depth_km      REAL,
  magnitude     REAL,
  place         TEXT,
  time_ms       INTEGER,            -- real event origin time (epoch ms) as reported by the source; NULL if unreported
  regional      INTEGER NOT NULL DEFAULT 0,
  url           TEXT,
  first_seen_at TEXT NOT NULL       -- when THIS system first recorded it -- an ingestion audit trail, not the event's own time
);
CREATE INDEX IF NOT EXISTS idx_world_quake_history_time ON world_quake_history(time_ms);
CREATE INDEX IF NOT EXISTS idx_world_quake_history_source ON world_quake_history(source);

CREATE TABLE IF NOT EXISTS cities (
  name      TEXT PRIMARY KEY,
  lat       REAL NOT NULL,
  lng       REAL NOT NULL,
  mmi_label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_scores (
  region TEXT PRIMARY KEY,
  score  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS model_performance (
  id        INTEGER PRIMARY KEY CHECK (id = 1),
  version   TEXT NOT NULL,
  precision REAL NOT NULL,
  recall    REAL NOT NULL,
  f1        REAL NOT NULL,
  accuracy  REAL NOT NULL,
  tp INTEGER, fp INTEGER, fn INTEGER, tn INTEGER
);

CREATE TABLE IF NOT EXISTS sources_static (
  name       TEXT PRIMARY KEY,   -- TMD | GISTDA | NASA (ENVIRO + USGS are computed live)
  color_var  TEXT NOT NULL,
  depth      REAL,
  latency_sec REAL,
  confidence  REAL,
  loc_err_km  REAL,
  note        TEXT,
  mag_offset  REAL NOT NULL DEFAULT 0   -- offset applied to the live event magnitude, for illustration
);

CREATE TABLE IF NOT EXISTS services (
  name          TEXT PRIMARY KEY,
  forced_status TEXT,     -- NULL = derive from real health check; else 'watch'/'critical' override for demo
  note          TEXT
);

CREATE TABLE IF NOT EXISTS roles (
  role        TEXT PRIMARY KEY,
  users_count INTEGER NOT NULL,
  permissions TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backups (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  path       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detector_config (
  id              INTEGER PRIMARY KEY CHECK (id = 1),
  stalta_threshold REAL NOT NULL,
  pga_calibration  REAL NOT NULL   -- multiplies peak |amplitude| of the synthetic signal into an estimated PGA (Gal)
);

CREATE TABLE IF NOT EXISTS telegram_config (
  id        INTEGER PRIMARY KEY CHECK (id = 1),
  bot_token TEXT,
  chat_id   TEXT,
  enabled   INTEGER NOT NULL DEFAULT 0
);

-- Real physical hardware nodes (e.g. the Heltec WiFi LoRa 32 V4 + GY-91
-- prototype in firmware/prototype_node) reporting their OWN onboard sensors
-- over Wi-Fi -- entirely separate from `stations` above, which is ENVIRO's
-- simulated 7-station seismic network with in-memory waveform/STA-LTA
-- buffers (see simulator.py). A real node has no waveform pipeline; it just
-- periodically reports what its sensors measured (temperature, pressure,
-- battery, accelerometer/gyro, a simple vibration flag) for display on the
-- "สถานีตรวจวัด" dashboard page (see routes/nodes.py).
CREATE TABLE IF NOT EXISTS real_nodes (
  node_id           TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  api_key           TEXT NOT NULL,   -- sent back by the node as the X-Node-Key header on every upload
  lat               REAL,
  lng               REAL,
  region            TEXT,
  created_at        TEXT NOT NULL,
  last_seen         TEXT,            -- NULL until its first successful telemetry upload
  temperature_c     REAL,
  pressure_hpa      REAL,
  battery_v         REAL,
  battery_pct       INTEGER,
  accel_x           REAL,
  accel_y           REAL,
  accel_z           REAL,
  gyro_x            REAL,
  gyro_y            REAL,
  gyro_z            REAL,
  roll_deg          REAL,
  pitch_deg         REAL,
  vibration_g       REAL,
  vibration_active  INTEGER NOT NULL DEFAULT 0,
  bmp_ok            INTEGER NOT NULL DEFAULT 0,
  imu_ok            INTEGER NOT NULL DEFAULT 0,
  uptime_s          INTEGER,
  is_simulated      INTEGER NOT NULL DEFAULT 0, -- 1 for the 7 generated nodes in server/node_simulator.py, 0 for a genuine physical device
  paused            INTEGER NOT NULL DEFAULT 0  -- admin/operator-set "force offline" for testing (see routes/nodes.py set_node_status) -- node_simulator.py skips ticking a paused node, and it always reads as offline regardless of last_seen
);

-- Short rolling per-node history (pruned in routes/nodes.py, ~5 min at the
-- node's 1-reading/sec upload rate) purely to draw a small recent-trend
-- sparkline on the dashboard -- not meant as a real time-series archive.
CREATE TABLE IF NOT EXISTS real_node_log (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id          TEXT NOT NULL,
  ts               TEXT NOT NULL,
  temperature_c    REAL,
  pressure_hpa     REAL,
  battery_pct      INTEGER,
  vibration_g      REAL,
  vibration_active INTEGER NOT NULL DEFAULT 0,
  accel_x          REAL,  -- one reading/upload (~1 Hz) -- a coarse fallback trend chart when a node's firmware doesn't send the high-rate "wave" burst (see routes/nodes.py node_waveform's low_res branch)
  accel_y          REAL,
  accel_z          REAL
);
CREATE INDEX IF NOT EXISTS idx_real_node_log_node_ts ON real_node_log(node_id, ts);

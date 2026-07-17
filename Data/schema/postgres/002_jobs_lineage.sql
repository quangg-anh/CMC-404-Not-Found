-- =========================================================
-- 002_jobs_lineage.sql - Jobs, job_events, lineage, van_ban_files
-- Nguon: Data/SYSTEM_DATA.md §4.2
-- Phu thuoc: 001_init.sql (enums job_status, visibility)
-- =========================================================

-- ---------- jobs ----------
CREATE TABLE IF NOT EXISTS jobs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type         TEXT NOT NULL,               -- legal_ingest | parse | extract | diff | social_ingest | brief ...
  status       job_status NOT NULL DEFAULT 'queued',
  stage        TEXT,                         -- buoc hien tai trong pipeline
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs (type);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs (created_at DESC);

DROP TRIGGER IF EXISTS trg_jobs_updated ON jobs;
CREATE TRIGGER trg_jobs_updated BEFORE UPDATE ON jobs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- job_events (timeline stepper) ----------
CREATE TABLE IF NOT EXISTS job_events (
  id         BIGSERIAL PRIMARY KEY,
  job_id     UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  stage      TEXT NOT NULL,
  status     job_status NOT NULL,
  message    TEXT,
  at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events (job_id, at);

-- ---------- lineage (replay tu raw checksum) ----------
CREATE TABLE IF NOT EXISTS lineage (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_checksum   TEXT NOT NULL,
  parse_version  TEXT,
  extract_model  TEXT,
  graph_revision TEXT,
  van_ban_id     TEXT,                       -- -> Neo4j VanBanPhapLuat.vb_id
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lineage_checksum ON lineage (raw_checksum);
CREATE INDEX IF NOT EXISTS idx_lineage_vanban ON lineage (van_ban_id);

-- ---------- van_ban_files (mirror metadata file goc) ----------
CREATE TABLE IF NOT EXISTS van_ban_files (
  file_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  van_ban_id  TEXT NOT NULL,                 -- -> Neo4j VanBanPhapLuat.vb_id
  filename    TEXT NOT NULL,
  mime        TEXT,
  storage_key TEXT NOT NULL,                 -- -> MinIO object key {yyyy}/{mm}/{checksum}/{filename}
  checksum    TEXT NOT NULL,
  visibility  visibility NOT NULL DEFAULT 'internal',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (van_ban_id, checksum)              -- immutable: khong lap cung checksum tren 1 VB
);
CREATE INDEX IF NOT EXISTS idx_files_vanban ON van_ban_files (van_ban_id);
CREATE INDEX IF NOT EXISTS idx_files_visibility ON van_ban_files (visibility);

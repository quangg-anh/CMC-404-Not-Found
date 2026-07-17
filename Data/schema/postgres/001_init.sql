-- =========================================================
-- 001_init.sql - Users, RBAC, enums dung chung, system_config
-- Nguon: Data/SYSTEM_DATA.md §4.2 + Backend/SYSTEM_BACKEND.md §2.1
-- Auto-apply: docker-entrypoint-initdb.d (lan init dau tien)
-- Idempotent: guard CREATE TYPE bang DO block; bang dung IF NOT EXISTS.
-- =========================================================

-- gen_random_uuid() co san tu PG13 core; van tao pgcrypto neu can crypt().
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- Enums dung chung ----------
DO $$ BEGIN
  CREATE TYPE user_role AS ENUM
    ('admin_phap_che','admin_truyen_thong','admin_ops','citizen','anonymous');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE visibility AS ENUM ('public','internal');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE job_status AS ENUM
    ('queued','running','success','error','needs_review');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE brief_status AS ENUM ('draft','review','published','archived');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE dexuat_status AS ENUM ('draft','ready','exported');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE alert_status AS ENUM ('open','triaged','closed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE media_type AS ENUM ('text','image','audio','video');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------- Trigger cap nhat updated_at ----------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

-- ---------- users ----------
CREATE TABLE IF NOT EXISTS users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT NOT NULL UNIQUE,
  full_name       TEXT,
  role            user_role NOT NULL DEFAULT 'citizen',
  hashed_password TEXT NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);

DROP TRIGGER IF EXISTS trg_users_updated ON users;
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- system_config ----------
-- Nguon threshold link/NLI, feature flags (SYSTEM_DATA §4.2)
CREATE TABLE IF NOT EXISTS system_config (
  key         TEXT PRIMARY KEY,
  value       JSONB NOT NULL,
  description TEXT,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_config_updated ON system_config;
CREATE TRIGGER trg_config_updated BEFORE UPDATE ON system_config
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Config mac dinh (an toan chay lai)
INSERT INTO system_config (key, value, description) VALUES
  ('link_score_threshold', '0.62', 'Nguong tao canh BaiDang->Khoan (BE2)'),
  ('nli_confidence_threshold', '0.7', 'Nguong confidence nhan doi chieu'),
  ('embedding_dim', '1024', 'Dim vector khop model (bge-m3). Doi phai bao BE2.'),
  ('feature_flags', '{"social":false,"brief":false}', 'Bat/tat phan he theo Phase')
ON CONFLICT (key) DO NOTHING;

-- =========================================================
-- 004_retention_audit.sql - Phase C: retention + audit publish + read-only role
-- Nguon: Data/SYSTEM_DATA.md §7, §9 (Phase C), §4.2
-- Phu thuoc: 001-003.
-- Idempotent.
-- =========================================================

-- ---------- Retention: danh dau thoi diem archive de ap policy ----------
ALTER TABLE briefs      ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
ALTER TABLE suggestions ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

-- Tu dong set archived_at khi status chuyen sang 'archived'
CREATE OR REPLACE FUNCTION set_archived_at() RETURNS trigger AS $$
BEGIN
  IF NEW.status::text = 'archived' AND (OLD.status::text IS DISTINCT FROM 'archived') THEN
    NEW.archived_at = now();
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_briefs_archived ON briefs;
CREATE TRIGGER trg_briefs_archived BEFORE UPDATE ON briefs
  FOR EACH ROW EXECUTE FUNCTION set_archived_at();

-- Config retention (ngay giu ban draft/archived truoc khi don dep)
INSERT INTO system_config (key, value, description) VALUES
  ('retention_draft_days',    '90',  'So ngay giu brief/suggestion o trang thai draft'),
  ('retention_archived_days', '365', 'So ngay giu ban archived truoc khi xoa')
ON CONFLICT (key) DO NOTHING;

-- ---------- Audit publish: view tong hop su kien xuat ban ----------
CREATE OR REPLACE VIEW v_publish_audit AS
SELECT a.id, a.actor, u.email AS actor_email, a.action, a.resource_id, a.detail, a.at
FROM audit_log a
LEFT JOIN users u ON u.id = a.actor
WHERE a.action IN ('publish_brief', 'archive_brief', 'export_suggest');

-- ---------- Read-only role (bao cao) - SYSTEM_DATA §7 ----------
-- Mat khau doi qua .env / secret manager tren moi truong that.
DO $$ BEGIN
  CREATE ROLE app_be_ro LOGIN PASSWORD 'change_me_ro';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

GRANT USAGE ON SCHEMA public TO app_be_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_be_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app_be_ro;

-- ---------- Citizen API role (PG limited) - SYSTEM_DATA §7 ----------
-- Citizen KHONG truy cap Neo4j truc tiep; chi doc mot so bang qua BE3.
DO $$ BEGIN
  CREATE ROLE app_citizen_api LOGIN PASSWORD 'change_me_citizen';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

GRANT USAGE ON SCHEMA public TO app_citizen_api;
GRANT SELECT ON briefs, van_ban_files TO app_citizen_api;

-- =========================================================
-- 003_content_publish.sql - briefs, suggestions, alerts, audit_log
-- Nguon: Data/SYSTEM_DATA.md §4.2
-- Cac bang mirror node Neo4j de query/filter nhanh + audit.
-- Source of truth noi dung/citation van la Neo4j; day la ban chieu.
-- Phu thuoc: 001_init.sql (enums brief_status, dexuat_status, alert_status, media_type)
-- =========================================================

-- ---------- briefs (mirror BaiTomTat) ----------
CREATE TABLE IF NOT EXISTS briefs (
  id           UUID PRIMARY KEY,             -- = Neo4j BaiTomTat.uuid
  tieu_de      TEXT,
  media_type   media_type NOT NULL DEFAULT 'text',
  status       brief_status NOT NULL DEFAULT 'draft',
  citations    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{khoan_id, quote}]
  created_by   UUID REFERENCES users(id),
  published_at TIMESTAMPTZ,
  published_by UUID REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_briefs_status ON briefs (status);

DROP TRIGGER IF EXISTS trg_briefs_updated ON briefs;
CREATE TRIGGER trg_briefs_updated BEFORE UPDATE ON briefs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- suggestions (mirror DeXuatDinhChinh) ----------
CREATE TABLE IF NOT EXISTS suggestions (
  id            UUID PRIMARY KEY,            -- = Neo4j DeXuatDinhChinh.uuid
  draft_text    TEXT,
  alert_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,
  khoan_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,
  claim_labels  JSONB NOT NULL DEFAULT '[]'::jsonb,
  status        dexuat_status NOT NULL DEFAULT 'draft',
  created_by    UUID REFERENCES users(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions (status);

DROP TRIGGER IF EXISTS trg_suggestions_updated ON suggestions;
CREATE TRIGGER trg_suggestions_updated BEFORE UPDATE ON suggestions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- alerts (mirror AlertMeta) ----------
CREATE TABLE IF NOT EXISTS alerts (
  id         UUID PRIMARY KEY,               -- = Neo4j AlertMeta.uuid
  chu_de     TEXT,
  khoan_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
  severity   TEXT,
  volume     INTEGER NOT NULL DEFAULT 0,
  status     alert_status NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts (status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts (severity);

DROP TRIGGER IF EXISTS trg_alerts_updated ON alerts;
CREATE TRIGGER trg_alerts_updated BEFORE UPDATE ON alerts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- audit_log ----------
-- Moi publish / export / ghi KG deu log (SYSTEM_BACKEND §9.4)
CREATE TABLE IF NOT EXISTS audit_log (
  id          BIGSERIAL PRIMARY KEY,
  actor       UUID REFERENCES users(id),
  action      TEXT NOT NULL,                 -- publish_brief | export_suggest | write_kg ...
  resource_id TEXT,
  detail      JSONB NOT NULL DEFAULT '{}'::jsonb,
  at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log (action, at);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log (actor, at);

-- =========================================================
-- Seed users test (Phase A): 1 admin + 1 citizen
-- Mat khau bam bang pgcrypto bcrypt. CHI dung cho dev.
--   admin@local   / admin123   (role admin_phap_che)
--   citizen@local / citizen123 (role citizen)
-- Idempotent: ON CONFLICT (email) DO NOTHING.
-- =========================================================

INSERT INTO users (email, full_name, role, hashed_password) VALUES
  ('admin@local',   'Admin Phap Che Test', 'admin_phap_che', crypt('admin123',   gen_salt('bf'))),
  ('citizen@local', 'Citizen Test',        'citizen',        crypt('citizen123', gen_salt('bf')))
ON CONFLICT (email) DO NOTHING;

-- Lineage mau cho VB seed (replay tracking)
-- lineage khong co unique key tu nhien -> dung WHERE NOT EXISTS de seed idempotent.
INSERT INTO lineage (raw_checksum, parse_version, extract_model, graph_revision, van_ban_id)
SELECT 'seed-checksum-nd012024', 'seed-v1', 'manual-seed', 'r1', 'ND-01-2024::2024-01-15'
WHERE NOT EXISTS (
  SELECT 1 FROM lineage WHERE raw_checksum = 'seed-checksum-nd012024'
);

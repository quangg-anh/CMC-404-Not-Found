-- =========================================================
-- Demo content seed: lights up Admin "Alerts" and Citizen "News".
-- Idempotent via fixed UUIDs. Safe to re-run.
-- Alerts reference Khoản canonical IDs digitized into Neo4j/Qdrant.
-- =========================================================

INSERT INTO alerts (id, chu_de, khoan_ids, severity, volume, status) VALUES
  ('a1111111-1111-1111-1111-111111111111', 'Nồng độ cồn khi điều khiển xe mô tô',
     '["168/2024/ND-CP::D6.K1"]'::jsonb, 'high', 42, 'open'),
  ('a2222222-2222-2222-2222-222222222222', 'Mức phạt vi phạm giao thông đường bộ',
     '["168/2024/ND-CP::D6.K2"]'::jsonb, 'medium', 17, 'open'),
  ('a3333333-3333-3333-3333-333333333333', 'Tịch thu phương tiện khi tái phạm',
     '["168/2024/ND-CP::D6.K2"]'::jsonb, 'low', 5, 'triaged')
ON CONFLICT (id) DO NOTHING;

INSERT INTO briefs (id, tieu_de, media_type, status, citations, published_at) VALUES
  ('b1111111-1111-1111-1111-111111111111',
     'Mức phạt nồng độ cồn với xe mô tô theo Nghị định 168/2024',
     'text', 'published',
     '[{"khoan_id":"168/2024/ND-CP::D6.K1","quote":"Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với người điều khiển xe mô tô mà trong máu hoặc hơi thở có nồng độ cồn chưa vượt quá 50 miligam trên 100 mililít máu.","van_ban":"168/2024/ND-CP","dieu":"Điều 6"}]'::jsonb,
     now()),
  ('b2222222-2222-2222-2222-222222222222',
     'Những điểm mới về xử phạt giao thông người dân cần biết',
     'text', 'published',
     '[{"khoan_id":"168/2024/ND-CP::D6.K2","quote":"Tịch thu phương tiện và tước giấy phép lái xe từ 22 tháng đến 24 tháng đối với hành vi tái phạm.","van_ban":"168/2024/ND-CP","dieu":"Điều 6"}]'::jsonb,
     now())
ON CONFLICT (id) DO NOTHING;

-- =========================================================
-- 010_brief_noi_dung.sql — nội dung bài viết trên briefs
-- Idempotent: ADD COLUMN IF NOT EXISTS
-- =========================================================

ALTER TABLE briefs ADD COLUMN IF NOT EXISTS noi_dung TEXT;

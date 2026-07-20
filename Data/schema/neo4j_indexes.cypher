// =========================================================
// Neo4j indexes - toi uu truy van KG
// Contract: Data/schema/ontology.json; temporal rollout: docs/architecture/lawgic-core-execution-plan-v2.md
// Ap dung:  cat neo4j_indexes.cypher | cypher-shell -u neo4j -p <pw>
// Idempotent: IF NOT EXISTS.
// =========================================================

// ---------- Range/lookup indexes ----------
// Tra cuu Khoan theo con tro embedding (vector nam o Qdrant)
CREATE INDEX khoan_embedding_id IF NOT EXISTS
  FOR (k:Khoan) ON (k.embedding_id);

// Lookup Khoan theo van ban (duyet cay nhanh)
CREATE INDEX khoan_van_ban_id IF NOT EXISTS
  FOR (k:Khoan) ON (k.van_ban_id);

// Filter VB cong khai cho Citizen
CREATE INDEX vanban_visibility IF NOT EXISTS
  FOR (v:VanBanPhapLuat) ON (v.visibility);

// Filter VB theo trang thai hieu luc
CREATE INDEX vanban_trang_thai IF NOT EXISTS
  FOR (v:VanBanPhapLuat) ON (v.trang_thai);

// Filter tin tom tat theo trang thai publish
CREATE INDEX baitomtat_status IF NOT EXISTS
  FOR (t:BaiTomTat) ON (t.status);

// Hang doi alert theo trang thai
CREATE INDEX alertmeta_status IF NOT EXISTS
  FOR (a:AlertMeta) ON (a.status);

// De xuat dinh chinh theo trang thai
CREATE INDEX dexuat_status IF NOT EXISTS
  FOR (x:DeXuatDinhChinh) ON (x.status);

// Bai dang theo thoi gian (loc theo cua so thoi gian MXH)
CREATE INDEX baidang_thoi_gian IF NOT EXISTS
  FOR (b:BaiDang) ON (b.thoi_gian);

// ---------- Fulltext (optional) ----------
// Tim kiem toan van tren noi dung Khoan (ho tro hybrid retrieve)
CREATE FULLTEXT INDEX khoan_noidung_ft IF NOT EXISTS
  FOR (k:Khoan) ON EACH [k.noi_dung];

// Immutable Dieu/Khoan/Diem v2 lexical source. Canonical text is hydrated after ranking.
CREATE FULLTEXT INDEX legal_provision_text_ft IF NOT EXISTS
  FOR (p:LegalProvision) ON EACH [p.noi_dung, p.tieu_de];

// =========================================================
// Phase B - MXH (Social)
// =========================================================

// Tra cuu YKien theo bai dang goc (lay claim cua 1 BaiDang)
CREATE INDEX ykien_baidang IF NOT EXISTS
  FOR (y:YKien) ON (y.bai_dang_id);

// Loc bai dang theo nen tang (dashboard MXH)
CREATE INDEX baidang_platform IF NOT EXISTS
  FOR (b:BaiDang) ON (b.platform);

// Fulltext noi dung bai dang (ho tro phan cum chu de / tim kiem MXH)
CREATE FULLTEXT INDEX baidang_noidung_ft IF NOT EXISTS
  FOR (b:BaiDang) ON EACH [b.noi_dung];

// Fulltext ten chu de
CREATE FULLTEXT INDEX chude_ten_ft IF NOT EXISTS
  FOR (c:ChuDe) ON EACH [c.ten];

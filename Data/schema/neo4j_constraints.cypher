// =========================================================
// Neo4j constraints - Knowledge Graph phap luat
// Nguon: Data/SYSTEM_DATA.md §4.1 + Backend/SYSTEM_BACKEND.md §3
// Ap dung:  cat neo4j_constraints.cypher | cypher-shell -u neo4j -p <pw>
// Luu y: Community Edition chi ho tro UNIQUE constraint.
//        Existence/property-type constraint (IS NOT NULL) can Enterprise.
//        Cac invariant con lai (vd GAN_CO_CAN_KIEM_CHUNG.score/method)
//        duoc enforce o tang Backend, xem ontology.json.
// Idempotent: dung IF NOT EXISTS -> chay lai an toan.
// =========================================================

// ---------- Van ban & phan cap Dieu/Khoan/Diem ----------
CREATE CONSTRAINT vanban_id IF NOT EXISTS
  FOR (v:VanBanPhapLuat) REQUIRE v.vb_id IS UNIQUE;

// dieu_id = {so_hieu_norm}::D{dieu}  (DB de xuat, thong nhat pattern voi khoan_id)
CREATE CONSTRAINT dieu_id IF NOT EXISTS
  FOR (d:Dieu) REQUIRE d.dieu_id IS UNIQUE;

CREATE CONSTRAINT khoan_id IF NOT EXISTS
  FOR (k:Khoan) REQUIRE k.khoan_id IS UNIQUE;

CREATE CONSTRAINT diem_id IF NOT EXISTS
  FOR (p:Diem) REQUIRE p.diem_id IS UNIQUE;

// ---------- Thuc the phap ly (key = uuid) ----------
CREATE CONSTRAINT chuthe_uuid IF NOT EXISTS
  FOR (n:ChuThe) REQUIRE n.uuid IS UNIQUE;
CREATE CONSTRAINT nghiavu_uuid IF NOT EXISTS
  FOR (n:NghiaVu) REQUIRE n.uuid IS UNIQUE;
CREATE CONSTRAINT quyenloi_uuid IF NOT EXISTS
  FOR (n:QuyenLoi) REQUIRE n.uuid IS UNIQUE;
CREATE CONSTRAINT hanhvicam_uuid IF NOT EXISTS
  FOR (n:HanhViCam) REQUIRE n.uuid IS UNIQUE;
CREATE CONSTRAINT thoihan_uuid IF NOT EXISTS
  FOR (n:ThoiHan) REQUIRE n.uuid IS UNIQUE;
CREATE CONSTRAINT chetai_uuid IF NOT EXISTS
  FOR (n:CheTai) REQUIRE n.uuid IS UNIQUE;

// ---------- Mang xa hoi (Phase B) ----------
CREATE CONSTRAINT baidang_ext IF NOT EXISTS
  FOR (b:BaiDang) REQUIRE (b.platform, b.external_id) IS UNIQUE;

CREATE CONSTRAINT chude_slug IF NOT EXISTS
  FOR (c:ChuDe) REQUIRE c.slug IS UNIQUE;

CREATE CONSTRAINT ykien_uuid IF NOT EXISTS
  FOR (y:YKien) REQUIRE y.uuid IS UNIQUE;

CREATE CONSTRAINT alertmeta_uuid IF NOT EXISTS
  FOR (a:AlertMeta) REQUIRE a.uuid IS UNIQUE;

// ---------- Noi dung xuat ban & dinh chinh (Phase C) ----------
CREATE CONSTRAINT baitomtat_uuid IF NOT EXISTS
  FOR (t:BaiTomTat) REQUIRE t.uuid IS UNIQUE;

CREATE CONSTRAINT dexuatdinhchinh_uuid IF NOT EXISTS
  FOR (x:DeXuatDinhChinh) REQUIRE x.uuid IS UNIQUE;

// ---------- File goc ----------
CREATE CONSTRAINT vanbanfile_uuid IF NOT EXISTS
  FOR (f:VanBanFile) REQUIRE f.uuid IS UNIQUE;

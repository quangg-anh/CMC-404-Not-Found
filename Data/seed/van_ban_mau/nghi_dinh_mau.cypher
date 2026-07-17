// =========================================================
// Seed van ban mau (GIA LAP - phuc vu dev/test)
// Nghi dinh 01/2024/ND-CP (mau) - cau truc Dieu-Khoan-Diem ro rang
// MERGE idempotent: chay lai khong tao trung (invariant §5 SYSTEM_DATA).
// LUU Y: cypher-shell chay moi cau (;) la 1 transaction rieng -> bien KHONG
//        song giua cac cau. Vi vay moi quan he phai MATCH lai node theo key.
// =========================================================

// ---------- Nodes ----------
MERGE (v:VanBanPhapLuat {vb_id: 'ND-01-2024::2024-01-15'})
SET v.so_hieu = '01/2024/ND-CP',
    v.so_hieu_norm = 'ND-01-2024',
    v.ten = 'Nghi dinh quy dinh mau ve xu phat vi pham hanh chinh (du lieu gia lap)',
    v.loai_vb = 'Nghi dinh',
    v.co_quan = 'Chinh phu',
    v.ngay_ban_hanh = date('2024-01-15'),
    v.ngay_hieu_luc = date('2024-03-01'),
    v.trang_thai = 'hieu_luc',
    v.visibility = 'public',
    v.file_ids = [];

MERGE (d1:Dieu {dieu_id: 'ND-01-2024::D1'})
SET d1.so_dieu = '1', d1.tieu_de = 'Pham vi dieu chinh', d1.van_ban_id = 'ND-01-2024::2024-01-15';

MERGE (d2:Dieu {dieu_id: 'ND-01-2024::D2'})
SET d2.so_dieu = '2', d2.tieu_de = 'Muc phat va thoi han', d2.van_ban_id = 'ND-01-2024::2024-01-15';

MERGE (k11:Khoan {khoan_id: 'ND-01-2024::D1.K1'})
SET k11.so_khoan = '1',
    k11.noi_dung = 'Nghi dinh nay quy dinh ve hanh vi vi pham hanh chinh, hinh thuc xu phat va muc phat trong linh vuc mau.',
    k11.van_ban_id = 'ND-01-2024::2024-01-15', k11.dieu_so = '1', k11.embedding_id = 'khoan::ND-01-2024::D1.K1';

MERGE (k12:Khoan {khoan_id: 'ND-01-2024::D1.K2'})
SET k12.so_khoan = '2',
    k12.noi_dung = 'Doi tuong ap dung bao gom to chuc, ca nhan co hanh vi vi pham hanh chinh quy dinh tai Nghi dinh nay.',
    k12.van_ban_id = 'ND-01-2024::2024-01-15', k12.dieu_so = '1', k12.embedding_id = 'khoan::ND-01-2024::D1.K2';

MERGE (k21:Khoan {khoan_id: 'ND-01-2024::D2.K1'})
SET k21.so_khoan = '1',
    k21.noi_dung = 'Phat tien tu 1.000.000 dong den 3.000.000 dong doi voi mot trong cac hanh vi sau day:',
    k21.van_ban_id = 'ND-01-2024::2024-01-15', k21.dieu_so = '2', k21.embedding_id = 'khoan::ND-01-2024::D2.K1';

MERGE (k22:Khoan {khoan_id: 'ND-01-2024::D2.K2'})
SET k22.so_khoan = '2',
    k22.noi_dung = 'Thoi han thuc hien bien phap khac phuc hau qua la 30 ngay ke tu ngay nhan duoc quyet dinh.',
    k22.van_ban_id = 'ND-01-2024::2024-01-15', k22.dieu_so = '2', k22.embedding_id = 'khoan::ND-01-2024::D2.K2';

MERGE (p21a:Diem {diem_id: 'ND-01-2024::D2.K1.Pa'})
SET p21a.ky_hieu = 'a', p21a.noi_dung = 'Khong niem yet cong khai theo quy dinh;', p21a.khoan_id = 'ND-01-2024::D2.K1';

MERGE (p21b:Diem {diem_id: 'ND-01-2024::D2.K1.Pb'})
SET p21b.ky_hieu = 'b', p21b.noi_dung = 'Ke khai khong day du thong tin theo mau quy dinh.', p21b.khoan_id = 'ND-01-2024::D2.K1';

MERGE (ct:ChuThe {uuid: 'seed-chuthe-tochuc-canhan'})
SET ct.mo_ta = 'To chuc, ca nhan vi pham hanh chinh', ct.nguon_khoan_id = 'ND-01-2024::D1.K2';

MERGE (nv:NghiaVu {uuid: 'seed-nghiavu-niemyet'})
SET nv.mo_ta = 'Niem yet cong khai theo quy dinh', nv.nguon_khoan_id = 'ND-01-2024::D2.K1';

MERGE (th:ThoiHan {uuid: 'seed-thoihan-30ngay'})
SET th.mo_ta = 'Thoi han khac phuc hau qua', th.nguon_khoan_id = 'ND-01-2024::D2.K2';

MERGE (ncp:CheTai {uuid: 'seed-chetai-phattien'})
SET ncp.mo_ta = 'Phat tien tu 1 den 3 trieu dong', ncp.nguon_khoan_id = 'ND-01-2024::D2.K1';

// ---------- Relationships (moi cau tu MATCH lai theo key) ----------
MATCH (v:VanBanPhapLuat {vb_id:'ND-01-2024::2024-01-15'}), (d:Dieu {dieu_id:'ND-01-2024::D1'}) MERGE (v)-[:CO_DIEU]->(d);
MATCH (v:VanBanPhapLuat {vb_id:'ND-01-2024::2024-01-15'}), (d:Dieu {dieu_id:'ND-01-2024::D2'}) MERGE (v)-[:CO_DIEU]->(d);

MATCH (d:Dieu {dieu_id:'ND-01-2024::D1'}), (k:Khoan {khoan_id:'ND-01-2024::D1.K1'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-01-2024::D1'}), (k:Khoan {khoan_id:'ND-01-2024::D1.K2'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-01-2024::D2'}), (k:Khoan {khoan_id:'ND-01-2024::D2.K1'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-01-2024::D2'}), (k:Khoan {khoan_id:'ND-01-2024::D2.K2'}) MERGE (d)-[:CO_KHOAN]->(k);

MATCH (k:Khoan {khoan_id:'ND-01-2024::D2.K1'}), (p:Diem {diem_id:'ND-01-2024::D2.K1.Pa'}) MERGE (k)-[:CO_DIEM]->(p);
MATCH (k:Khoan {khoan_id:'ND-01-2024::D2.K1'}), (p:Diem {diem_id:'ND-01-2024::D2.K1.Pb'}) MERGE (k)-[:CO_DIEM]->(p);

MATCH (k:Khoan {khoan_id:'ND-01-2024::D2.K1'}), (nv:NghiaVu {uuid:'seed-nghiavu-niemyet'}) MERGE (k)-[:QUY_DINH]->(nv);
MATCH (k:Khoan {khoan_id:'ND-01-2024::D2.K2'}), (th:ThoiHan {uuid:'seed-thoihan-30ngay'}) MERGE (k)-[:QUY_DINH]->(th);
MATCH (k:Khoan {khoan_id:'ND-01-2024::D2.K1'}), (c:CheTai {uuid:'seed-chetai-phattien'}) MERGE (k)-[:QUY_DINH]->(c);

MATCH (nv:NghiaVu {uuid:'seed-nghiavu-niemyet'}), (ct:ChuThe {uuid:'seed-chuthe-tochuc-canhan'}) MERGE (nv)-[:AP_DUNG_CHO]->(ct);
MATCH (c:CheTai {uuid:'seed-chetai-phattien'}), (ct:ChuThe {uuid:'seed-chuthe-tochuc-canhan'}) MERGE (c)-[:AP_DUNG_CHO]->(ct);

RETURN 'seed_vanban_ok' AS ket_qua;

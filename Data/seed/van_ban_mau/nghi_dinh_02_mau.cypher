// =========================================================
// Seed van ban mau #2 (GIA LAP) - Nghi dinh 02/2024/ND-CP (mau)
// Muc dich: bo sung so luong Khoan de gold set du >=20 dong.
// Chu de: quan ly thong tin va bao ve du lieu (du lieu gia lap).
// MERGE idempotent; moi quan he tu MATCH lai theo key.
// =========================================================

// ---------- Van ban ----------
MERGE (v:VanBanPhapLuat {vb_id: 'ND-02-2024::2024-02-20'})
SET v.so_hieu = '02/2024/ND-CP',
    v.so_hieu_norm = 'ND-02-2024',
    v.ten = 'Nghi dinh mau ve quan ly va bao ve du lieu (du lieu gia lap)',
    v.loai_vb = 'Nghi dinh',
    v.co_quan = 'Chinh phu',
    v.ngay_ban_hanh = date('2024-02-20'),
    v.ngay_hieu_luc = date('2024-04-01'),
    v.trang_thai = 'hieu_luc',
    v.visibility = 'public',
    v.file_ids = [];

// ---------- Dieu 1..4 ----------
MERGE (d1:Dieu {dieu_id:'ND-02-2024::D1'}) SET d1.so_dieu='1', d1.tieu_de='Nguyen tac chung', d1.van_ban_id='ND-02-2024::2024-02-20';
MERGE (d2:Dieu {dieu_id:'ND-02-2024::D2'}) SET d2.so_dieu='2', d2.tieu_de='Trach nhiem to chuc', d2.van_ban_id='ND-02-2024::2024-02-20';
MERGE (d3:Dieu {dieu_id:'ND-02-2024::D3'}) SET d3.so_dieu='3', d3.tieu_de='Thoi han va luu tru', d3.van_ban_id='ND-02-2024::2024-02-20';
MERGE (d4:Dieu {dieu_id:'ND-02-2024::D4'}) SET d4.so_dieu='4', d4.tieu_de='Xu ly vi pham', d4.van_ban_id='ND-02-2024::2024-02-20';

// ---------- Khoan (16) ----------
MERGE (k:Khoan {khoan_id:'ND-02-2024::D1.K1'}) SET k.so_khoan='1', k.noi_dung='To chuc, ca nhan phai bao dam an toan thong tin trong qua trinh thu thap du lieu.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='1', k.embedding_id='khoan::ND-02-2024::D1.K1';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D1.K2'}) SET k.so_khoan='2', k.noi_dung='Viec xu ly du lieu ca nhan phai duoc su dong y cua chu the du lieu.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='1', k.embedding_id='khoan::ND-02-2024::D1.K2';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D1.K3'}) SET k.so_khoan='3', k.noi_dung='Nghiem cam mua ban du lieu ca nhan trai phep duoi moi hinh thuc.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='1', k.embedding_id='khoan::ND-02-2024::D1.K3';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D1.K4'}) SET k.so_khoan='4', k.noi_dung='Du lieu phai duoc thu thap dung muc dich da thong bao cho chu the du lieu.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='1', k.embedding_id='khoan::ND-02-2024::D1.K4';

MERGE (k:Khoan {khoan_id:'ND-02-2024::D2.K1'}) SET k.so_khoan='1', k.noi_dung='To chuc phai chi dinh nguoi phu trach bao ve du lieu ca nhan.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='2', k.embedding_id='khoan::ND-02-2024::D2.K1';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D2.K2'}) SET k.so_khoan='2', k.noi_dung='To chuc phai thong bao cho co quan quan ly khi xay ra su co lo lot du lieu.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='2', k.embedding_id='khoan::ND-02-2024::D2.K2';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D2.K3'}) SET k.so_khoan='3', k.noi_dung='To chuc phai xay dung quy trinh noi bo ve bao ve du lieu ca nhan.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='2', k.embedding_id='khoan::ND-02-2024::D2.K3';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D2.K4'}) SET k.so_khoan='4', k.noi_dung='To chuc phai dinh ky danh gia rui ro doi voi hoat dong xu ly du lieu.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='2', k.embedding_id='khoan::ND-02-2024::D2.K4';

MERGE (k:Khoan {khoan_id:'ND-02-2024::D3.K1'}) SET k.so_khoan='1', k.noi_dung='Thoi han luu tru du lieu ca nhan khong qua nam nam ke tu ngay thu thap.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='3', k.embedding_id='khoan::ND-02-2024::D3.K1';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D3.K2'}) SET k.so_khoan='2', k.noi_dung='Sau khi het thoi han luu tru, du lieu phai duoc xoa hoac an danh.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='3', k.embedding_id='khoan::ND-02-2024::D3.K2';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D3.K3'}) SET k.so_khoan='3', k.noi_dung='Chu the du lieu co quyen yeu cau xoa du lieu ca nhan cua minh.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='3', k.embedding_id='khoan::ND-02-2024::D3.K3';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D3.K4'}) SET k.so_khoan='4', k.noi_dung='To chuc phai phan hoi yeu cau cua chu the du lieu trong thoi han ba muoi ngay.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='3', k.embedding_id='khoan::ND-02-2024::D3.K4';

MERGE (k:Khoan {khoan_id:'ND-02-2024::D4.K1'}) SET k.so_khoan='1', k.noi_dung='Phat tien tu 20.000.000 dong den 50.000.000 dong doi voi hanh vi lam lo lot du lieu.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='4', k.embedding_id='khoan::ND-02-2024::D4.K1';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D4.K2'}) SET k.so_khoan='2', k.noi_dung='Truong hop tai pham thi muc phat duoc tang len gap hai lan.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='4', k.embedding_id='khoan::ND-02-2024::D4.K2';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D4.K3'}) SET k.so_khoan='3', k.noi_dung='Ngoai phat tien, to chuc vi pham buoc phai khac phuc hau qua da gay ra.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='4', k.embedding_id='khoan::ND-02-2024::D4.K3';
MERGE (k:Khoan {khoan_id:'ND-02-2024::D4.K4'}) SET k.so_khoan='4', k.noi_dung='Ca nhan vi pham co the bi cam dam nhiem cong viec xu ly du lieu trong hai nam.', k.van_ban_id='ND-02-2024::2024-02-20', k.dieu_so='4', k.embedding_id='khoan::ND-02-2024::D4.K4';

// ---------- Relationships ----------
MATCH (v:VanBanPhapLuat {vb_id:'ND-02-2024::2024-02-20'}), (d:Dieu {dieu_id:'ND-02-2024::D1'}) MERGE (v)-[:CO_DIEU]->(d);
MATCH (v:VanBanPhapLuat {vb_id:'ND-02-2024::2024-02-20'}), (d:Dieu {dieu_id:'ND-02-2024::D2'}) MERGE (v)-[:CO_DIEU]->(d);
MATCH (v:VanBanPhapLuat {vb_id:'ND-02-2024::2024-02-20'}), (d:Dieu {dieu_id:'ND-02-2024::D3'}) MERGE (v)-[:CO_DIEU]->(d);
MATCH (v:VanBanPhapLuat {vb_id:'ND-02-2024::2024-02-20'}), (d:Dieu {dieu_id:'ND-02-2024::D4'}) MERGE (v)-[:CO_DIEU]->(d);

MATCH (d:Dieu {dieu_id:'ND-02-2024::D1'}), (k:Khoan {khoan_id:'ND-02-2024::D1.K1'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D1'}), (k:Khoan {khoan_id:'ND-02-2024::D1.K2'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D1'}), (k:Khoan {khoan_id:'ND-02-2024::D1.K3'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D1'}), (k:Khoan {khoan_id:'ND-02-2024::D1.K4'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D2'}), (k:Khoan {khoan_id:'ND-02-2024::D2.K1'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D2'}), (k:Khoan {khoan_id:'ND-02-2024::D2.K2'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D2'}), (k:Khoan {khoan_id:'ND-02-2024::D2.K3'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D2'}), (k:Khoan {khoan_id:'ND-02-2024::D2.K4'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D3'}), (k:Khoan {khoan_id:'ND-02-2024::D3.K1'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D3'}), (k:Khoan {khoan_id:'ND-02-2024::D3.K2'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D3'}), (k:Khoan {khoan_id:'ND-02-2024::D3.K3'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D3'}), (k:Khoan {khoan_id:'ND-02-2024::D3.K4'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D4'}), (k:Khoan {khoan_id:'ND-02-2024::D4.K1'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D4'}), (k:Khoan {khoan_id:'ND-02-2024::D4.K2'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D4'}), (k:Khoan {khoan_id:'ND-02-2024::D4.K3'}) MERGE (d)-[:CO_KHOAN]->(k);
MATCH (d:Dieu {dieu_id:'ND-02-2024::D4'}), (k:Khoan {khoan_id:'ND-02-2024::D4.K4'}) MERGE (d)-[:CO_KHOAN]->(k);

RETURN 'seed_vanban_02_ok' AS ket_qua;

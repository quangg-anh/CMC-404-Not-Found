# Database / Data Platform — Người phụ trách Data (1 người)

> Phân công tổng: `TEAM_ASSIGNMENT.md`  
> Ontology vận hành: khớp `Backend/SYSTEM_BACKEND.md` §3  
> Owner duy nhất: **schema, migrate, seed, backup, quyền truy cập kho dữ liệu**

---

## 1. Sứ mệnh

Thiết kế và vận hành **toàn bộ tầng persistence** của đồ thị tri thức:

1. **Neo4j** — Knowledge Graph (quan hệ + nguyên văn Khoản = source of truth citation)  
2. **PostgreSQL** — meta vận hành (users, jobs, audit, briefs, files)  
3. **Qdrant** — vector retrieve  
4. **Redis** — queue + cache  
5. **Object store (MinIO / `Data/raw`)** — file luật gốc bất biến  
6. **Thư mục `Data/`** — raw → interim → processed → seed → gold → schema  

DB **không** viết business API FastAPI hay UI — chỉ cung cấp schema, connection, script, tài liệu cho BE1/BE2/BE3.

---

## 2. Hệ thống BẮT BUỘC phải cài & quản lý

| Hệ thống | Phiên bản gợi ý | Vai trò chi tiết | Port dev |
|---|---|---|---|
| **Docker Compose** | mới nhất | Một lệnh nâng toàn stack data | — |
| **Neo4j 5.x** Community/Enterprise | KG + Cypher constraints/indexes | `7474`, `7687` |
| **PostgreSQL 16** | Users, RBAC mirror, jobs, lineage, briefs, suggestions, alert meta, file meta | `5432` |
| **Qdrant 1.x** | Collections embedding | `6333` |
| **Redis 7** | Broker Arq/Celery + cache | `6379` |
| **MinIO** | S3 API cho PDF/DOCX/HTML | `9000` (API), `9001` (console) |
| **neo4j-admin / cypher-shell** | Migrate, dump, load | — |
| **psql / migrate tool** | Alembic (Python) hoặc Flyway | — |
| **qdrant CLI / HTTP** | Tạo collection, snapshot | — |

Optional: Neo4j Bloom (visualize), Grafana (monitor disk/connections).

---

## 3. Cấu trúc thư mục `Data/`

```
Data/
  SYSTEM_DATA.md              # file này
  docker-compose.data.yml     # Neo4j+PG+Redis+Qdrant+MinIO
  .env.example                # credentials mẫu (không commit secret thật)

  schema/
    neo4j_constraints.cypher
    neo4j_indexes.cypher
    ontology.json             # danh sách label + rel + property
    postgres/
      001_init.sql
      002_jobs_lineage.sql
      003_content_publish.sql
    qdrant/
      collections.json        # khoan, baidang, chude
    extract_khoan.schema.json # JSON Schema cho BE1 NER output

  raw/                        # IMMUTABLE — file gốc theo checksum
    legal/{yyyy}/{checksum}/...
    social/{yyyy}/{checksum}/...

  interim/                    # tree parse JSON trước khi lên graph
  processed/                  # entities + edges sẵn MERGE
  embeddings/                 # optional manifest id↔vector location

  seed/
    van_ban_mau/              # 1–2 nghị định mẫu
    social_mau/               # vài BaiDang giả lập
    load_seed.sh

  gold/
    citations.json            # câu hỏi → quote đúng
    links.json                # bài → khoan_id đúng
    nli.json                  # claim–khoản → label

  backups/
    neo4j/
    postgres/
    qdrant/
```

---

## 4. Kiến trúc dữ liệu 4 kho (chi tiết)

### 4.1 Neo4j — Knowledge Graph

**Labels (node):**  
`VanBanPhapLuat`, `Dieu`, `Khoan`, `Diem`, `ChuThe`, `NghiaVu`, `QuyenLoi`, `HanhViCam`, `ThoiHan`, `CheTai`, `BaiDang`, `ChuDe`, `YKien`, `AlertMeta`, `BaiTomTat`, `DeXuatDinhChinh`, `VanBanFile`

**Relationships:** đúng `SYSTEM_BACKEND.md` §3.2  
(`CO_DIEU`, `CO_KHOAN`, `CO_DIEM`, `QUY_DINH`, `AP_DUNG_CHO`, `THAY_THE`, `SUA_DOI`, `THAO_LUAN_VE`, `LIEN_QUAN`, `GAN_CO_CAN_KIEM_CHUNG`, `DOI_CHIEU`, `TOM_TAT_TU`, `DE_XUAT_CHO`, `CAN_CU`, `CO_FILE`)

**Canonical keys:**

| Node | Key |
|---|---|
| VanBanPhapLuat | `vb_id` = hash(`so_hieu_norm` + `ngay_ban_hanh`) |
| Khoan | `khoan_id` = `{so_hieu_norm}::D{dieu}.K{khoan}` |
| Diem | `diem_id` = `{khoan_id}.P{ky_hieu}` |
| BaiDang | `(platform, external_id)` |
| ChuDe | `slug` |

**Constraints tối thiểu (`neo4j_constraints.cypher`):**

```cypher
CREATE CONSTRAINT vanban_id IF NOT EXISTS FOR (v:VanBanPhapLuat) REQUIRE v.vb_id IS UNIQUE;
CREATE CONSTRAINT khoan_id IF NOT EXISTS FOR (k:Khoan) REQUIRE k.khoan_id IS UNIQUE;
CREATE CONSTRAINT diem_id IF NOT EXISTS FOR (d:Diem) REQUIRE d.diem_id IS UNIQUE;
CREATE CONSTRAINT baidang_ext IF NOT EXISTS FOR (b:BaiDang) REQUIRE (b.platform, b.external_id) IS UNIQUE;
CREATE CONSTRAINT chude_slug IF NOT EXISTS FOR (c:ChuDe) REQUIRE c.slug IS UNIQUE;
```

**Indexes:** `Khoan.embedding_id`, `VanBanPhapLuat.visibility`, `BaiTomTat.status`, fulltext optional trên `Khoan.noi_dung`.

**Invariant DB enforce (documentation + trigger logic BE):**

- Cạnh `GAN_CO_CAN_KIEM_CHUNG` bắt buộc có `score`, `method`.  
- Citizen chỉ đọc node VB `visibility='public'` và brief `status='published'` (filter ở BE3; DB có thể tạo read-only user).

### 4.2 PostgreSQL — Meta vận hành

Bảng tối thiểu:

| Bảng | Mục đích |
|---|---|
| `users` | id, email, role (`admin_phap_che`…), hashed_password |
| `jobs` | id, type, status, stage, payload_json, error, created_at, updated_at |
| `job_events` | timeline stepper |
| `lineage` | raw_checksum, parse_version, extract_model, graph_revision, van_ban_id |
| `van_ban_files` | file_id, van_ban_id, filename, mime, storage_key, checksum, visibility |
| `briefs` | mirror/status BaiTomTat cho query nhanh + audit |
| `suggestions` | mirror DeXuatDinhChinh |
| `alerts` | mirror AlertMeta (list/filter nhanh) |
| `audit_log` | actor, action (`publish_brief`, `export_suggest`, …), resource_id, at |
| `system_config` | threshold link score, NLI, feature flags |

Alembic versioning: mọi thay đổi schema qua migration — **cấm** sửa tay prod.

### 4.3 Qdrant — Vector

| Collection | Vector size | Payload bắt buộc | Ai ghi |
|---|---|---|---|
| `khoan` | theo model (vd. 1024 bge-m3) | `khoan_id`, `van_ban_id`, `dieu`, `text_preview` | BE1 (sau extract) |
| `baidang` | cùng dim | `bai_dang_id`, `chu_de`, `platform` | BE2 |
| `chude` | cùng dim | `slug`, `ten` | BE2 |

**Quy tắc:** Vector **không** là nguồn trích dẫn. Mọi citation phải lấy `noi_dung` từ Neo4j bằng `khoan_id`.

### 4.4 Redis

| Key pattern | Mục đích |
|---|---|
| `arq:queue` / celery | Job broker |
| `qa:cache:{hash}` | Semantic/exact cache QA đã validate |
| `ratelimit:citizen:qa:{user}` | Chống abuse |

### 4.5 Object store

- Bucket `legal-raw`, `social-raw` (social chỉ metadata cần thiết).  
- Object key: `{yyyy}/{mm}/{checksum}/{filename}`.  
- Immutable: không overwrite cùng checksum.  
- Signed URL TTL ngắn cho Citizen download file `visibility=public`.

---

## 5. Luồng dữ liệu DB phải đảm bảo

```
RAW (MinIO) 
  → INTERIM parse JSON (Data/interim)
  → PROCESSED entities (Data/processed)
  → MERGE Neo4j + UPSERT Qdrant
  → Postgres lineage + job=success
```

Replay: từ `raw_checksum` chạy lại pipeline → cùng `khoan_id` (idempotent MERGE).

---

## 6. Seed & Gold (trách nhiệm DB chuẩn bị)

### Seed (Phase A)

- 1–2 văn bản luật/nghị định thật hoặc giả lập có cấu trúc Điều–Khoản–Điểm rõ.  
- Script `load_seed.sh`: constraints → load nodes → sample vectors (BE1 có thể re-embed).  
- 1 user admin + 1 user citizen test.

### Gold (đánh giá)

- `citations.json`: ≥ 20 Q–A với quote khớp substring.  
- `links.json`: ≥ 20 cặp bài–Khoản.  
- `nli.json`: phân bố đủ 3 nhãn.

---

## 7. Bảo mật & quyền truy cập

| User DB | Quyền |
|---|---|
| `app_be_rw` | BE đọc/ghi Neo4j+PG+Qdrant theo cần |
| `app_be_ro` (optional) | báo cáo |
| `app_citizen_api` | PG limited; Neo4j **không** direct — chỉ qua BE3 |
| Neo4j auth | bật password; không expose 7687 ra internet khi chưa harden |

- Secret trong `.env` / secret manager — không commit.  
- Backup mã hóa at-rest nếu triển khai production.

---

## 8. Backup & phục hồi

| Kho | Tần suất gợi ý | Công cụ |
|---|---|---|
| Neo4j | daily dump | `neo4j-admin database dump` |
| Postgres | daily | `pg_dump` |
| Qdrant | snapshot trước release | Qdrant snapshot API |
| MinIO | versioning bucket | MinIO versioning |

Test restore ít nhất 1 lần / Phase.

---

## 9. Việc DB theo Phase (checklist)

### Phase A

- [ ] `docker-compose.data.yml` chạy 5 service  
- [ ] Cypher constraints + indexes  
- [ ] Postgres migrations 001–003  
- [ ] Qdrant collection `khoan`  
- [ ] MinIO buckets + `.env.example`  
- [ ] Seed 1–2 VB + user test  
- [ ] Document connection strings cho BE  

### Phase B

- [ ] Collections `baidang`, `chude`  
- [ ] Bảng `alerts`, indexes MXH  
- [ ] Threshold config trong `system_config`  
- [ ] Backup script  

### Phase C

- [ ] Audit publish  
- [ ] Retention policy draft/archived  
- [ ] Gold sets đủ để chấm citation/link  
- [ ] Read-only checks / monitoring disk  

---

## 10. Contract với Backend / Frontend

| Đối tác | DB giao | DB nhận |
|---|---|---|
| **BE1** | Schema Khoản, MERGE mẫu, seed raw | Báo property thiếu khi parse |
| **BE2** | Schema MXH + vector collections | Threshold, dim embedding khi đổi model |
| **BE3** | Connection, migration version, signed URL policy | Không ALTER lệch Alembic |
| **FE** | Enum status/visibility ổn định (qua API) | Không query DB trực tiếp |

**Đổi ontology:** DB mở RFC ngắn trong PR → BE1/BE2/BE3 approve → merge schema trước code dùng label mới.

---

## 11. Tiêu chí Done Database

- `docker compose -f Data/docker-compose.data.yml up -d` healthy trong ≤ 3 phút máy dev.  
- Constraints Neo4j ngăn trùng `khoan_id`.  
- Seed load được; BE1 MERGE không lỗi schema.  
- Backup/restore thử thành công 1 lần.  
- Tài liệu `ontology.json` khớp 100% label đang dùng trên graph.  

---

## 12. Ví dụ thuộc tính tối thiểu (tham chiếu nhanh)

**Khoan:** `khoan_id`, `so_khoan`, `noi_dung`, `embedding_id`, `van_ban_id`, `dieu_so`  
**VanBanPhapLuat:** `vb_id`, `so_hieu`, `ten`, `ngay_hieu_luc`, `visibility`, `trang_thai`  
**BaiDang:** `platform`, `external_id`, `noi_dung`, `tac_gia_hash`, `thoi_gian`  
**DOI_CHIEU:** `label`, `score`  
**GAN_CO_CAN_KIEM_CHUNG:** `score`, `method`

Chi tiết đầy đủ đồng bộ với `Backend/SYSTEM_BACKEND.md` §3 — nếu lệch, **ưu tiên cập nhật cả hai file trong cùng PR**.

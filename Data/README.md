# Data Platform — Hướng dẫn cho Backend

> Vai trò: DB / Data Platform. Chi tiết thiết kế: `SYSTEM_DATA.md`.
> File này = tài liệu vận hành + **connection string** cho BE1/BE2/BE3 consume.
> DB **không** viết business API / UI — chỉ cung cấp schema, connection, script.

---

## 1. Khởi động toàn stack

```bash
cp Data/.env.example Data/.env          # rồi sửa mật khẩu trong Data/.env
docker compose -f Data/docker-compose.data.yml --env-file Data/.env up -d
docker compose -f Data/docker-compose.data.yml ps      # tất cả phải "healthy"
```

Tắt stack: `docker compose -f Data/docker-compose.data.yml down` (thêm `-v` để xóa cả dữ liệu volume).

Yêu cầu: Docker Desktop (WSL2 backend trên Windows). Stack healthy trong ≤ 3 phút máy dev.

---

## 2. Connection strings (dev, đọc từ `Data/.env`)

| Kho | Địa chỉ dev | Auth (mặc định `.env.example`) | Ghi chú |
|---|---|---|---|
| **Neo4j (Bolt)** | `bolt://localhost:7687` | user `neo4j` / `change_me_neo4j` | KG + nguyên văn Khoản = source of truth citation |
| **Neo4j (HTTP/Browser)** | `http://localhost:7474` | như trên | kiểm tra ontology thủ công |
| **PostgreSQL** | `postgresql://app_be_rw:change_me_pg@localhost:5432/legal_kg` | user `app_be_rw` | meta: users, jobs, lineage, briefs, alerts, audit |
| **Qdrant** | `http://localhost:6333` (gRPC `6334`) | — | collections: `khoan`, `baidang`, `chude` |
| **Redis** | `redis://localhost:6379/0` | — | queue Arq/Celery + cache QA |
| **MinIO (S3 API)** | `http://localhost:9000` | `minio_admin` / `change_me_minio` | bucket `legal-raw`, `social-raw` (versioning bật) |
| **MinIO (Console)** | `http://localhost:9001` | như trên | UI quản lý object |

Biến môi trường tương ứng: `NEO4J_URI`, `DATABASE_URL`, `QDRANT_URL`, `REDIS_URL`, `MINIO_ENDPOINT`, `EMBEDDING_DIM` — xem `Data/.env.example`.

> **Đổi mật khẩu production**: sửa `Data/.env`, không commit secret thật.

---

## 3. Áp schema & seed

### Postgres (tự động)
Migrations trong `schema/postgres/` được **auto-apply** lần đầu Postgres init (mount vào `docker-entrypoint-initdb.d`). Chạy theo thứ tự tên file: `001_ → 002_ → 003_`.

Áp lại thủ công (nếu cần) hoặc reset:
```bash
# reset sạch để chạy lại migrations từ đầu
docker compose -f Data/docker-compose.data.yml rm -sf postgres
docker volume rm legal-kg-data_postgres_data
docker compose -f Data/docker-compose.data.yml --env-file Data/.env up -d postgres
```

### Neo4j + seed + Qdrant collections (một lệnh)
```bash
bash Data/seed/load_seed.sh            # Linux/macOS/Git-Bash
# hoặc Windows PowerShell:
powershell -ExecutionPolicy Bypass -File Data/seed/load_seed.ps1
```
Script sẽ: nạp constraints + indexes → load VB mẫu → seed users → đảm bảo Qdrant collections.

User test sau seed: `admin@local` / `admin123` (admin_phap_che), `citizen@local` / `citizen123` (citizen).

---

## 4. Cấu trúc thư mục

```
Data/
  docker-compose.data.yml     # 5 service + minio-init
  .env.example                # credentials mẫu
  README.md                   # file này
  SYSTEM_DATA.md              # thiết kế đầy đủ
  schema/
    neo4j_constraints.cypher  # 17 UNIQUE constraints
    neo4j_indexes.cypher      # index + fulltext Khoan.noi_dung
    ontology.json             # nguồn chân lý label/rel/property/enum
    postgres/
      001_init.sql            # users, RBAC enums, system_config
      002_jobs_lineage.sql    # jobs, job_events, lineage, van_ban_files
      003_content_publish.sql # briefs, suggestions, alerts, audit_log
      004_retention_audit.sql # archived_at, v_publish_audit, read-only roles
    qdrant/
      collections.json        # spec khoan/baidang/chude (dim 1024)
      extract_khoan.schema.json # JSON Schema output NER BE1
  seed/
    van_ban_mau/nghi_dinh_mau.cypher, nghi_dinh_02_mau.cypher
    social_mau/baidang_mau.json
    users_seed.sql
    load_seed.sh / load_seed.ps1
  gold/
    citations.json            # >=20 Q-A, quote = substring nguyen van Khoan
    links.json                # >=20 bai -> expected_khoan_ids (precision@k)
    nli.json                  # >=20 claim-Khoan, 3 nhan khop/mau_thuan/khong_ro
    generate_gold.ps1         # sinh lai gold tu Neo4j (quote luon substring)
  backups/
    backup_all.sh/.ps1 · restore_all.sh/.ps1
    {neo4j,postgres,qdrant}/
```

### Gold sets (đánh giá QA/link/NLI)
Sinh lại từ dữ liệu seed trong Neo4j (quote đảm bảo là substring nguyên văn Khoản):
```bash
powershell -File Data/gold/generate_gold.ps1
```
Format khớp `Backend/scripts/eval_be2_gold.py`: `links.json`→`expected_khoan_ids`, `nli.json`→`premise`/`hypothesis`/`label`.

---

## 5. Contract với Backend (điểm phải nhớ)

| Đối tác | DB giao | Ràng buộc |
|---|---|---|
| **BE1** | schema Khoản, seed raw, MERGE mẫu (`nghi_dinh_mau.cypher`) | MERGE theo key (`khoan_id`, `dieu_id`…) để idempotent; báo property thiếu |
| **BE2** | collections `baidang`/`chude`, dim vector | đổi model embedding phải báo → cập nhật `EMBEDDING_DIM` + `system_config.embedding_dim` |
| **BE3** | connection, migration version, signed URL policy MinIO | **không** ALTER schema tay trên prod; đổi qua migration file mới |
| **FE** | enum status/visibility ổn định (qua API) | không query DB trực tiếp |

**Bất biến quan trọng:**
- Citation lấy `noi_dung` từ **Neo4j** bằng `khoan_id`; **vector không phải nguồn trích dẫn**.
- Citizen chỉ đọc VB `visibility='public'` và brief `status='published'` (filter ở BE3).
- Cạnh `GAN_CO_CAN_KIEM_CHUNG` bắt buộc có `score`, `method`; `DOI_CHIEU.label ∈ {khop, mau_thuan, khong_ro}`.
- Đổi ontology: mở RFC trong PR → BE1/BE2/BE3 approve → cập nhật **cả** `ontology.json` và `SYSTEM_BACKEND.md` §3 cùng lúc.

---

## 6. Backup (tham chiếu nhanh, xem `SYSTEM_DATA.md` §8)

| Kho | Lệnh gợi ý | Online? |
|---|---|---|
| Postgres | `docker exec legal_postgres pg_dump -U app_be_rw legal_kg > Data/backups/postgres/dump.sql` | ✅ online |
| Qdrant | Snapshot API: `POST http://localhost:6333/collections/{name}/snapshots` | ✅ online |
| MinIO | versioning bucket (đã bật) | ✅ online |
| Neo4j | **Community cần DB offline** (xem dưới) | ⚠️ offline |

Neo4j Community — dump phải dừng DB trước (`neo4j-admin database backup` online chỉ có ở Enterprise).

**Script tự động** (backup cả 3 kho + restore Neo4j, tự stop/start Neo4j an toàn):
```bash
# Backup: Postgres pg_dump + Qdrant snapshots + Neo4j dump
bash Data/backups/backup_all.sh
powershell -File Data/backups/backup_all.ps1        # Windows

# Restore Neo4j từ dump gần nhất (ghi đè DB hiện tại)
bash Data/backups/restore_all.sh
powershell -File Data/backups/restore_all.ps1       # Windows
```
Đã test backup + restore thành công (marker node revert đúng, seed nguyên vẹn).

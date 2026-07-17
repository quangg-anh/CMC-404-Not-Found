# Integration Notes — trạng thái ghép Backend ↔ Frontend ↔ Database

> Người ghi: DB / Data Platform. Ngày: 2026-07-17.
> Mục đích: nêu rõ chỗ đã khớp và chỗ lệch giữa 3 phần, kèm đề xuất sửa.
> Quyết định contract cần cả team approve (xem `TEAM_ASSIGNMENT.md` §3, `SYSTEM_DATA.md` §10).

---

## 1. Ma trận kết nối (audit tĩnh trên code hiện tại)

| Cặp | Trạng thái | Ghi chú |
|---|---|---|
| DB ↔ BE — env/connection | ✅ Khớp | BE đọc đúng `DATABASE_URL`, `NEO4J_URI/USER/PASSWORD`, `QDRANT_URL` (trùng `Data/.env`). Có fallback Fake khi DB offline (`app/api/deps.py`). |
| DB ↔ BE — Neo4j label/rel | ✅ Khớp | `BaiDang`, `ChuDe`, `Khoan`, `AlertMeta`, `YKien` + `THAO_LUAN_VE`, `GAN_CO_CAN_KIEM_CHUNG`, `DOI_CHIEU` đúng ontology. |
| DB ↔ BE — Neo4j **key property** | 🟡 Lệch | Xem §3. |
| DB ↔ BE — Qdrant | ✅ Khớp | Collection `khoan/baidang/chude`, dim 1024, Cosine. |
| DB ↔ BE — Postgres | ✅ **Đã fix (2026-07-17)** | BE2 sửa adapter khớp cột/enum. Xem §2. |
| BE ↔ FE | ❌ Chưa nối | FE dùng dữ liệu mock, chưa gọi API. Xem §4. |
| Chạy chung | ✅ BE boot OK | `uvicorn` chạy, `GET /health` → 200. Xem §7. |

### Cập nhật 2026-07-17 (sau khi BE2 fix)
- ✅ **Postgres**: `postgres_content.py` đã map đúng `briefs(id,tieu_de,media_type,status,citations)`, `suggestions(id,draft_text,alert_ids,khoan_ids,claim_labels,status)`, đọc `alerts` theo cột; cast enum + cấp `id` từ `uuid` Neo4j. **Khớp schema.**
- ✅ **Neo4j key**: `AlertMeta {uuid}` và `YKien {uuid}` (uuid5 deterministic) — khớp constraint `alertmeta_uuid`/`ykien_uuid`.
- ✅ **Ontology**: DB đã thêm cạnh `LIEN_QUAN: BaiDang → YKien` (adapter `save_nli` dùng) vào `ontology.json` để đồng bộ contract.
- ❌ **Blocker mới (BE scope)**: BE không boot — xem §7.

**Quyết định team (2026-07-17):** giữ schema theo `SYSTEM_DATA.md` §4.2 → **BE2 sửa adapter** cho khớp (hướng B). DB **không** đổi cột.

---

## 2. Postgres — lệch giữa adapter BE2 và schema DB (CẦN BE2 SỬA)

File adapter: `Backend/app/adapters/postgres_content.py`.

### 2.1 `briefs`
- Adapter đang ghi: `INSERT INTO briefs (title, status, payload_json) ... RETURNING id`.
- Schema thật (`Data/schema/postgres/003_content_publish.sql`): cột là
  `id (UUID PK, KHÔNG default), tieu_de, media_type, status, citations (JSONB), created_by, published_at, published_by`.
- **Vấn đề:** không có cột `title`, `payload_json`; `id` không tự sinh → INSERT hiện tại fail.
- **Đề xuất sửa adapter:**
  ```sql
  INSERT INTO briefs (id, tieu_de, media_type, status, citations, created_by)
  VALUES ($1, $2, $3, $4, $5, $6)
  ON CONFLICT (id) DO UPDATE SET tieu_de=EXCLUDED.tieu_de, status=EXCLUDED.status,
       citations=EXCLUDED.citations
  RETURNING id;
  ```
  - `id` = `BaiTomTat.uuid` bên Neo4j (briefs là bản mirror — dùng chung uuid).
  - `citations` là JSONB `[{khoan_id, quote}]` (không dùng `payload_json`).

### 2.2 `suggestions`
- Adapter: `INSERT INTO suggestions (status, payload_json) RETURNING id`.
- Schema: `id (UUID PK, KHÔNG default), draft_text, alert_ids (JSONB), khoan_ids (JSONB), claim_labels (JSONB), status, created_by`.
- **Đề xuất sửa adapter:**
  ```sql
  INSERT INTO suggestions (id, draft_text, alert_ids, khoan_ids, claim_labels, status, created_by)
  VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id;
  ```
  - `id` = `DeXuatDinhChinh.uuid` bên Neo4j.

### 2.3 `alerts`
- Adapter đọc: `SELECT id, payload_json FROM alerts WHERE id = ANY($1::uuid[])`.
- Schema: `id (UUID PK), chu_de, khoan_ids (JSONB), severity, volume, status`. Không có `payload_json`.
- **Đề xuất sửa adapter:** đọc cột trực tiếp
  ```sql
  SELECT id, chu_de, khoan_ids, severity, volume, status FROM alerts WHERE id = ANY($1::uuid[]);
  ```

> Ghi chú: `id` các bảng mirror **cố ý không có default** vì dùng chung UUID với node Neo4j (traceability). Nếu BE muốn Postgres tự sinh id độc lập, đó là một RFC đổi schema — cần thống nhất trước.

---

## 3. Neo4j — lệch key property (CẦN CHỐT RFC)

File: `Backend/app/adapters/neo4j_social.py`.

| Node | Ontology DB (key) | Backend đang MERGE theo | Đề xuất |
|---|---|---|---|
| `AlertMeta` | `uuid` (constraint `alertmeta_uuid`) | `{alert_id}` | Chốt 1 khóa duy nhất: hoặc BE set `uuid`, hoặc DB đổi constraint sang `alert_id`. |
| `YKien` | `uuid` (constraint `ykien_uuid`) | `{bai_dang_id, claim_hash}` | Tương tự: thêm constraint composite `(bai_dang_id, claim_hash)` hoặc BE set `uuid`. |

- Hiện **không gây lỗi runtime** (Community Edition không ép tồn tại property; uniqueness bỏ qua null), nhưng **uniqueness không được đảm bảo** cho `AlertMeta`/`YKien` → có thể tạo trùng.
- DB sẵn sàng thêm constraint composite nếu team chọn theo backend (chỉ cần 1 dòng trong `neo4j_constraints.cypher`).

---

## 4. Frontend — chưa wire API (việc của FE)

- `Frontend/apps/citizen/src/features/ask/AskPage.tsx`: trả lời AI **giả lập** bằng `setTimeout`, citation hardcode.
- `Frontend/apps/admin/src/features/dashboard/Dashboard.tsx`: số liệu tĩnh ("1,204", "42", "99.8%").
- Không có api-client / `fetch` / `axios` / `VITE_API_URL` trong source.
- Backend đã bật CORS cho `http://localhost:5173`. FE cần thêm lớp gọi API theo `SYSTEM_FRONTEND.md` §8.1 (map path đã có sẵn trong `Backend/app/main.py`).

---

## 5. Cách chạy 3 phần chung (khi cần kiểm tra end-to-end)

1. **DB** (đang chạy): `docker compose -f Data/docker-compose.data.yml --env-file Data/.env up -d` → `load_seed`.
2. **Backend** (cần Python 3.11+): venv → `pip install -r Backend/requirements.txt` + `fastapi uvicorn` → set env kết nối → `uvicorn app.main:app --port 8000`. (Chi tiết trong hướng dẫn chạy backend.)
3. **Frontend**: `npm install` → `npm run dev` (Vite, cổng 5173) — nhưng cần wire API trước mới lấy được dữ liệu thật.

Thứ tự phụ thuộc: **DB → BE → FE**.

---

## 6. Việc cần làm để "3 phần nối nhau thật"

- [x] **BE2**: sửa `postgres_content.py` theo §2 (map đúng cột, cấp `id` từ uuid Neo4j). ✅ 2026-07-17
- [x] **BE2 + DB**: chốt key `AlertMeta`/`YKien` (§3) → BE dùng `uuid`, DB thêm cạnh `LIEN_QUAN BaiDang→YKien`. ✅
- [ ] **BE**: sửa ImportError để `uvicorn` boot được (§7).
- [ ] **FE**: thêm api-client + thay mock bằng gọi API thật (§4).
- [ ] **Team**: chạy end-to-end 1 lần (DB seed → BE ingest/QA → FE hiển thị).
- [x] **DB**: schema/seed/gold/backup sẵn sàng, connection khớp env BE.

---

## 7. Backend boot — ĐÃ FIX (2026-07-17)

`uvicorn app.main:app` trước đây fail ngay khi import (exit 1):

```
ImportError: cannot import name 'verify_and_publish_brief'
from 'app.services.publish_gate'  ... app/services/brief_service.py line 7
```

- Nguyên nhân: `publish_gate.py` export **class** `PublishGateService` (method `verify_and_publish_brief(brief_id, actor, brief_data)` → trả về `tuple[bool, dict, list]`), nhưng `brief_service.py` import như hàm module-level **và** gọi sai thứ tự tham số.
- **Đã sửa:** đổi import sang `PublishGateService`; `publish_brief()` giờ khởi tạo `PublishGateService(pool, driver)` và gọi `verify_and_publish_brief(brief_id, user_token, item)`, xử lý tuple trả về.
- **Xác nhận:** `python -c "import app.main"` OK; `uvicorn ... :8010` → `GET /health` = `200 {"status":"ok"}`.

### 7.1 Còn lại (BE functional, KHÔNG gây crash)
`brief_service.py` (list/get/generate/update) vẫn dùng cột **không có trong schema**: `tuc_danh`, `citations_json`, và sinh id dạng `brief-xxxx` (không phải UUID). Các thao tác này bọc trong `try/except: pass` nên **không crash**, nhưng sẽ **không ghi được vào Postgres thật** (khác với `postgres_content.py` đã đúng: `tieu_de`, `citations`, `media_type`, id=UUID). BE nên hợp nhất `brief_service.py` theo đúng cột schema `003_content_publish.sql`.

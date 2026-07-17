# BE1 — Legal Pipeline (Người Backend 1/3)

> Phân công tổng: `TEAM_ASSIGNMENT.md`  
> Contract: `Backend/SYSTEM_BACKEND.md` · Ontology: `Data/SYSTEM_DATA.md`  
> Module sở hữu: **1 (Parse), 2 (NER/RE), 4 (Version Diff)**

---

## 1. Sứ mệnh

Biến file luật thô (PDF/HTML/DOCX) thành **cây Điều–Khoản–Điểm + thực thể pháp lý + diff phiên bản**, rồi **ghi đúng** vào Neo4j + Vector theo schema DB phát hành.

BE1 **không** làm: API public FastAPI (BE3), MXH/NLI/Brief generate (BE2), UI (FE).

---

## 2. Hệ thống / thư viện BẮT BUỘC

| Hệ thống | Chi tiết dùng |
|---|---|
| Python 3.11+ | Package `app/pipelines/legal/` |
| **pdfplumber** + **PyMuPDF (fitz)** | PDF text; fallback khi layout lệch |
| **lxml** / BeautifulSoup | HTML nghị định |
| **python-docx** (optional) | DOCX |
| **Regex state machine** | Nhận diện `Điều`, `Khoản`, `Điểm` / `a)`, `b)` |
| **Pydantic v2** | JSON schema output parser + NER |
| Neo4j driver (`neo4j`) | MERGE node/edge theo schema DB |
| Qdrant client | Upsert embedding Khoản (gọi embed qua BE2 router) |
| MinIO / `Data/raw/` | Lưu file gốc + checksum |
| Postgres | Ghi `jobs`, `lineage`, `van_ban_files` (qua repo chung hoặc SQLAlchemy) |
| Redis + Arq/Celery | Worker: `legal_parse`, `legal_extract`, `legal_diff` |
| LLM local (Gemma gateway) | Fallback parse lệch chuẩn — **chỉ qua 9R-Shield router (BE2)** |
| pytest | Fixture VB mẫu trong `Data/seed/` |

---

## 3. Phạm vi code (thư mục)

```
Backend/app/
  pipelines/legal/
    crawler.py          # optional: tải từ URL danh mục
    ingest.py           # nhận file → object store + job
    parser.py           # Điều–Khoản–Điểm
    normalize.py        # số hiệu, canonical id
    extractor.py        # NER/RE schema-locked từng Khoản
    version_diff.py     # regex dẫn chiếu + similarity + LLM diff
  workers/
    legal_jobs.py
  domain/
    legal_schemas.py    # Pydantic khớp Data/schema
```

---

## 4. Việc cụ thể (checklist)

### Phase A (MVP) — bắt buộc

- [ ] `POST` ingest nội bộ: nhận file → checksum SHA-256 → MinIO/raw → tạo job `legal_ingest`
- [ ] Parser state machine: `VanBan → Dieu → Khoan → Diem`
- [ ] Canonical ID: `{so_hieu_norm}::D{n}.K{m}` (và `.P{ky_hieu}` cho Điểm)
- [ ] Flag `needs_review` khi parse confidence thấp / lệch format
- [ ] Fallback LLM local (schema JSON cố định) khi regex fail
- [ ] Extract mỗi Khoản: `ChuThe`, `NghiaVu`, `QuyenLoi`, `HanhViCam`, `ThoiHan`, `CheTai` → JSON validate
- [ ] Ghi Neo4j đúng relation `CO_DIEU`, `CO_KHOAN`, `CO_DIEM`, `QUY_DINH`, `AP_DUNG_CHO`
- [ ] Gọi embed service → upsert Qdrant collection `khoan` (payload: `khoan_id`, `van_ban_id`, text preview)
- [ ] Version diff: cặp VB cũ/mới → hunk `them|xoa|sua` + `method: explicit_ref|similarity|llm`
- [ ] Ghi quan hệ `THAY_THE` / `SUA_DOI` khi có căn cứ
- [ ] Lineage Postgres: `raw_checksum → parse_version → extract_model → graph_revision`

### Phase B

- [ ] Cải thiện parser VB scan/OCR-ish (nếu có)
- [ ] Hàng đợi review: payload rõ ràng cho FE `/admin/review`
- [ ] Metrics: parse_success_rate, extract_schema_fail_rate

### Phase C

- [ ] Hook: sau diff quan trọng → event để BE2/BE3 sinh Brief draft
- [ ] Idempotent replay từ checksum (chạy lại không nhân đôi node)

---

## 5. Contract với người khác

| Đối tác | BE1 đưa | BE1 nhận |
|---|---|---|
| **DB** | Yêu cầu index/constraint nếu thiếu | `Data/schema/neo4j_constraints.cypher`, JSON schema extract |
| **BE2** | Gọi `embed_texts()`, `llm_complete(task=parse|extract|diff)` | Router ổn định, timeout, schema lỗi rõ |
| **BE3** | Worker cập nhật job stage; domain objects sẵn | API ingest/jobs/diff gọi pipeline; không đổi ontology |
| **FE** | — | FE chỉ thấy kết quả qua API BE3 |

---

## 6. API / job mà BE1 phải hỗ trợ (BE3 expose)

| Job name | Trigger | Output |
|---|---|---|
| `legal_ingest` | `POST /admin/ingest/legal` | `van_ban_id`, files |
| `legal_parse` | sau ingest | tree JSON + needs_review |
| `legal_extract` | sau parse OK | entities trên từng Khoản |
| `legal_embed` | sau extract | vector ids |
| `legal_diff` | `POST /admin/legal/diff` hoặc auto cặp VB | hunks + edges version |

---

## 7. Tiêu chí Done BE1

- Seed 1–2 nghị định parse ≥ ngưỡng team (vd. 90% Khoản không `needs_review`).  
- Mọi Khoản trong Neo4j có `noi_dung` nguyên văn đủ để citation substring.  
- Diff trả được ít nhất một trong: dẫn chiếu tường minh hoặc similarity có score.  
- Không tạo node lệch label so với `Data/SYSTEM_DATA.md`.  
- Worker idempotent theo `checksum + pipeline_version`.

---

## 8. Rủi ro cần tránh

- Embed cả văn bản thay vì **từng Khoản**.  
- Gọi LLM thẳng không qua router.  
- Tự thêm edge MXH (phạm vi BE2).  
- Soft-delete sai làm mất lineage raw.

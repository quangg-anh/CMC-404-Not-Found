# Phân Công Nhóm 5 Người — Hệ Thống Đồ Thị Tri Thức Pháp Luật

> Nguồn chân lý: `base_core.md`  
> Chi tiết kỹ thuật: `Backend/SYSTEM_BACKEND.md` · `Frontend/SYSTEM_FRONTEND.md` · `Data/SYSTEM_DATA.md`  
> Thành phần: **3 Backend · 1 Frontend · 1 Database**

---

## 1. Sơ đồ trách nhiệm

```
                         ┌─────────────────────┐
                         │   Database (DB)      │
                         │ Neo4j · PG · Vector  │
                         │ Redis · ObjectStore  │
                         │ Schema · Seed · Backup│
                         └──────────┬──────────┘
                                    │ contract schema
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ BE1 Legal       │    │ BE2 Social+AI   │    │ BE3 API+QA      │
│ Parse·NER·Diff  │───►│ Topic·Link·NLI  │───►│ FastAPI·RAG     │
│ Ghi Neo4j/Vec   │    │ Alert·Brief·Sug │    │ Auth·Jobs·Gate  │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
         └──────────────────────┼──────────────────────┘
                                ▼
                    ┌───────────────────────┐
                    │ Frontend (FE)          │
                    │ Admin + Citizen        │
                    │ ui-legal · api-client  │
                    └───────────────────────┘
```

| Vai trò | File chi tiết | Module chính (`base_core`) | Deliverable chính |
|---|---|---|---|
| **BE1 — Legal Pipeline** | `Backend/ROLE_BE1_LEGAL_PIPELINE.md` | 1, 2, 4 | Ingest → Parse → Extract → Diff → nạp KG/Vector |
| **BE2 — Social & Intelligence** | `Backend/ROLE_BE2_SOCIAL_INTEL.md` | 3, 5, 6, 9a, 9b | MXH, link, NLI, Brief, Suggest, embedding/LLM router |
| **BE3 — API & QA Services** | `Backend/ROLE_BE3_API_QA_SERVICES.md` | 7, 8 + toàn bộ API | FastAPI Admin/Citizen, RAG QA, Auth, Jobs, PublishGate |
| **FE — Dual Portal** | `Frontend/ROLE_FRONTEND.md` | UI Admin + Citizen | 2 apps + shared packages, map API §8.1 |
| **DB — Data Platform** | `Data/SYSTEM_DATA.md` | Ontology + persistence | Schema Neo4j/PG/Qdrant, seed, backup, lineage |

---

## 2. Hệ thống / công cụ BẮT BUỘC phải dùng

### 2.1 Runtime & ngôn ngữ

| Hệ thống | Phiên bản gợi ý | Ai sở hữu chính | Mục đích |
|---|---|---|---|
| **Python** | 3.11+ | BE1, BE2, BE3, DB | Backend, pipeline, script migrate |
| **Node.js** | 20 LTS | FE | Vite monorepo Admin/Citizen |
| **TypeScript** | 5.x | FE | Type-safe UI + api-client |
| **Docker + Docker Compose** | mới nhất ổn định | DB (+ cả team) | Chạy Neo4j, Postgres, Redis, Qdrant local/dev |
| **Git** | — | cả team | nhánh theo role: `be1/*`, `be2/*`, `be3/*`, `fe/*`, `db/*` |

### 2.2 Persistence (DB lead setup, BE consume)

| Hệ thống | Vai trò | Port mặc định (dev) | Ai dùng |
|---|---|---|---|
| **Neo4j 5.x** | Knowledge Graph (source of truth quan hệ + nguyên văn Khoản) | `7474` HTTP / `7687` Bolt | DB, BE1 ghi, BE2 ghi MXH, BE3 đọc Graph/QA |
| **PostgreSQL 16** | Meta: users, jobs, audit, briefs, suggestions, files metadata | `5432` | DB, BE3 chính, BE1/BE2 ghi lineage |
| **Qdrant** (ưu tiên) hoặc **pgvector** | Embedding Khoản/Điểm/BaiDang | `6333` | DB setup, BE1/BE2 ghi, BE3 retrieve |
| **Redis 7** | Queue job + cache semantic QA | `6379` | DB setup, BE3 queue/cache, BE1/BE2 workers |
| **MinIO** (S3-compatible) hoặc local `Data/raw/` | Object store PDF/DOCX/HTML | `9000` | DB policy, BE1 ingest file, FE download qua API |

### 2.3 API & worker

| Hệ thống | Mục đích | Owner |
|---|---|---|
| **FastAPI** | API `/admin/*` + `/citizen/*` | BE3 |
| **Uvicorn / Gunicorn** | ASGI server | BE3 |
| **Arq** hoặc **Celery + Redis** | Worker pipeline dài | BE1/BE2 jobs, BE3 orchestrate status |
| **Pydantic v2** | Schema request/response + JSON extract | cả BE |
| **httpx / aiohttp** | Gọi LLM gateway, MXH API | BE2, BE3 |

### 2.4 NLP / AI

| Hệ thống | Mục đích | Owner |
|---|---|---|
| **LLM local (Gemma qua gateway)** | Parse fallback, extract nhẹ | BE1, BE2 |
| **9R-Shield LLM Router** | Route local vs large theo độ phức tạp/chi phí | BE2 sở hữu router; BE1/BE3 gọi |
| **Embedding `bge-m3` hoặc vietnamese-sbert** | Vector Khoản + topic MXH | BE2 |
| **NLI model (VN hoặc multilingual)** | Claim ↔ Khoản → khop/mau_thuan/khong_ro | BE2 |
| **GPTCache** (optional) + Redis | Semantic cache câu hỏi lặp | BE3 |
| **pdfplumber / PyMuPDF / lxml** | Đọc PDF/HTML luật | BE1 |

### 2.5 MXH (Phase B)

| Hệ thống | Mục đích | Owner | Lưu ý |
|---|---|---|---|
| **Facebook Graph API** | Thu thập thảo luận (nếu có quyền) | BE2 | Tôn trọng ToS, rate limit |
| **YouTube Data API** | Comment/video liên quan luật | BE2 | — |
| **Forum crawl có kiểm soát** | Bổ sung nguồn | BE2 | PII hash, không lưu thừa |

### 2.6 Frontend

| Hệ thống | Mục đích | Owner |
|---|---|---|
| **React 18 + Vite** | 2 apps: admin, citizen | FE |
| **TanStack Query (React Query)** | Server state, polling jobs/alerts | FE |
| **React Router** | IA theo `SYSTEM_FRONTEND.md` | FE |
| **vis-network** hoặc **Nivo/Cytoscape** | GraphCanvas Admin | FE |
| **Zod** | Validate response API phía client | FE |

### 2.7 Quan sát & chất lượng

| Hệ thống | Mục đích | Owner |
|---|---|---|
| **Prometheus + Grafana** (optional MVP: logging JSON) | Metrics parse/citation/refuse | BE3 + DB |
| **pytest** | Unit/integration BE | cả BE |
| **Playwright** hoặc Vitest+RTL | FE smoke | FE |
| **Neo4j Browser / Bloom** | Kiểm tra ontology thủ công | DB |

---

## 3. Ranh giới cứng (tránh đụng độ)

| Việc | Được làm | Không được làm |
|---|---|---|
| Đổi ontology node/edge | **DB** đề xuất → cả team approve | BE tự thêm label Neo4j lệch schema |
| Đổi path API `/admin/*` `/citizen/*` | **BE3** + cập nhật FE §8.1 cùng PR | FE tự bịa endpoint |
| Ghi embedding / gọi LLM | BE1 (Khoản sau extract), BE2 (MXH + brief/suggest), qua **router BE2** | FE gọi thẳng LLM |
| Publish tin Citizen | BE3 `PublishGate` + FE nút duyệt | BE2 tự `published` không qua gate |
| Seed / migrate DB | **DB** | BE merge schema “tay” trên prod |

**Contract giữa người:**  
- DB phát hành `Data/schema/*` + version.  
- BE3 phát hành OpenAPI (`/openapi.json`).  
- FE chỉ code theo OpenAPI + bảng map §8.1.

---

## 4. Lịch theo Phase (đồng bộ 5 người)

### Phase A — MVP (lõi luật + QA)

| Người | Việc phải xong |
|---|---|
| DB | Neo4j constraints, PG tables users/jobs/files, Qdrant collection `khoan`, Redis, MinIO/raw, seed 1–2 VB |
| BE1 | Parse Điều–Khoản–Điểm, NER schema-locked, Diff, ghi Neo4j+vector |
| BE2 | Embedding service + LLM router skeleton (BE1/BE3 gọi được) |
| BE3 | FastAPI skeleton, Auth RBAC, ingest/jobs/van-ban/diff/qa Admin, citizen QA filter public |
| FE | Admin: ingest, van-ban, diff, qa, jobs · Citizen: ask + citations |

### Phase B — MXH + Graph

| Người | Việc |
|---|---|
| DB | Index MXH, AlertMeta, backup policy |
| BE2 | Social ingest, topic, link, NLI, alerts |
| BE3 | API social/alerts/graph/review + dashboard summary |
| FE | MXH, alerts, graph explorer, review |
| BE1 | Ổn định parse trên VB lệch format + review flags |

### Phase C — Brief + Citizen hoàn chỉnh

| Người | Việc |
|---|---|
| BE2 | ContentBrief + ResponseSuggest generate |
| BE3 | Brief CRUD, PublishGate, suggestions API, citizen news/files |
| FE | Briefs, suggestions, citizen news + file download |
| DB | Audit publish, retention draft/archived |
| BE1 | Hỗ trợ trigger brief từ diff hunk |

---

## 5. Definition of Done chung

- Mọi Q&A / Brief có citation quote ∈ nguyên văn Khoản trong Neo4j.  
- Citizen không đọc được draft / alert / BaiDang thô.  
- Nhãn MXH chỉ `khop | mau_thuan | khong_ro`.  
- `docker compose up` chạy được stack tối thiểu (Neo4j+PG+Redis+Qdrant+API).  
- OpenAPI khớp FE §8.1; schema khớp `Data/SYSTEM_DATA.md`.

---

## 6. Mục lục file phân công

| File | Nội dung |
|---|---|
| `TEAM_ASSIGNMENT.md` | File này — tổng quan + stack bắt buộc |
| `Backend/ROLE_BE1_LEGAL_PIPELINE.md` | Việc BE1 chi tiết |
| `Backend/ROLE_BE2_SOCIAL_INTEL.md` | Việc BE2 chi tiết |
| `Backend/ROLE_BE3_API_QA_SERVICES.md` | Việc BE3 chi tiết |
| `Frontend/ROLE_FRONTEND.md` | Việc FE chi tiết |
| `Data/SYSTEM_DATA.md` | Việc DB + thiết kế data đầy đủ |
| `Backend/SYSTEM_BACKEND.md` | Kiến trúc backend (contract) |
| `Frontend/SYSTEM_FRONTEND.md` | Kiến trúc frontend (contract) |
| `base_core.md` | Đề bài & mục tiêu sản phẩm |

# LexSocial AI
*Được phát triển bởi đội ngũ **CMC 404 Not Found***

> Hệ thống Đồ thị Tri thức Pháp luật & Giám sát Mạng Xã hội mã nguồn mở, kết hợp AI để giảm thiểu rủi ro pháp lý.

Mã nguồn của dự án được **công khai hoàn toàn** (Open Source) nhằm mục đích giáo dục, nghiên cứu và phát triển cộng đồng.

---

## 📖 Bối cảnh & Mục tiêu

Từ **01/07/2026**, nhiều luật, nghị định, thông tư mới có hiệu lực. Nhu cầu nắm bắt tác động pháp lý nhanh chóng trở nên cấp thiết, đồng thời mạng xã hội bùng nổ thảo luận và dễ nảy sinh các hiểu lầm về quy định mới.

**LexSocial AI** được sinh ra với mục tiêu xây dựng một **Knowledge Graph (Đồ thị tri thức)** hợp nhất hai miền dữ liệu:
1. **Văn bản pháp luật** (chính thống, có cấu trúc).
2. **Dư luận Mạng Xã hội** (phi chính thống).

Dự án cung cấp hai phân hệ (Portal) phục vụ hai nhóm đối tượng khác nhau, chia sẻ chung một hệ thống Backend mạnh mẽ.

---

## 🌐 Giao diện Web & Phân hệ Hệ thống

Hệ thống LexSocial AI gồm **hai phân hệ UI trong một SPA** (`Frontend/apps/web`, cổng 5173):

### 1️⃣ Phân hệ Admin Dashboard (`/admin`)
*Dành cho cơ quan nhà nước, cán bộ pháp chế, giám sát truyền thông, quản trị dữ liệu.*

- Cung cấp bộ công cụ mạnh mẽ để cán bộ pháp chế quản lý kho dữ liệu luật, theo dõi biểu đồ thống kê từ mạng xã hội (đồ thị tri thức Admin dùng `react-force-graph-2d`).
- **Số hóa văn bản pháp luật**: Tải lên PDF/HTML, tự động bóc tách cấu trúc (Điều, Khoản, Điểm) bằng NLP, lưu vào Neo4j và Qdrant.
- **Theo dõi phiên bản (Version Diff)**: Tìm điểm khác biệt giữa các phiên bản luật, tự động tạo diff và ghi chú.
- **Giám sát dư luận (Social Listening)**: Thu thập dữ liệu từ mạng xã hội, phân loại chủ đề (Topic Classification), và đối chiếu mức độ khớp với luật hiện hành (NLI).
- **Cảnh báo rủi ro**: Xử lý các cảnh báo rủi ro theo thời gian thực (gắn nhãn `khớp / mâu thuẫn / không rõ`).
- **Gợi ý & Xuất bản**: Duyệt đề xuất đính chính truyền thông, và xuất bản nội dung (Publish) ra công chúng.

### 2️⃣ Phân hệ Citizen Portal (`/`)
*Dành cho người dân tra cứu.*

- Giao diện thiết kế tối giản, dễ thao tác, ưu tiên tính dễ đọc và truy cập nhanh.
- **Tra cứu công khai**: Tìm kiếm văn bản luật nhanh chóng, trực quan, không yêu cầu đăng nhập.
- **Tóm tắt luật thông minh**: Đọc các bản tin pháp luật được AI tóm tắt ngắn gọn, dễ hiểu.
- **Hỏi-đáp AI (RAG QA)**: Đặt câu hỏi pháp lý và nhận câu trả lời từ AI. Mọi kết quả hỏi đáp đều được trình bày rõ ràng, nhấn mạnh vào nguồn trích dẫn gốc **(Citation-first)** giúp người dân dễ dàng xác thực độ tin cậy của câu trả lời.

---

## ⚙️ Kiến trúc & Công nghệ

Hệ thống kết hợp các công nghệ tối ưu cho Web và AI hiện đại, tuân thủ kiến trúc Microservices và Monorepo.

### AI & Xử lý Ngữ nghĩa
- **LLM Router (9R-Shield):** Điều hướng linh hoạt giữa local model (Gemma) và API model tùy độ phức tạp của câu hỏi.
- **Embedding:** OpenAI-compatible API — mặc định `text-embedding-3-small` (dim **1536**). Cấu hình qua `BE2_OPENAI_*` / `BE2_EMBEDDING_*` trong `Backend/.env`.
- **Entailment gate (NLI):** pluggable. **Bản demo mặc định dùng heuristic** (token-overlap + chặn cứng khi lệch số/mã văn bản). Model transformers (vd. mDeBERTa) chỉ khi `BE2_NLI_TRANSFORMERS=1` và cài thêm deps — **không** claim “dùng BERT” trên demo.
- **Clarity Index:** `clarity_risk × log(volume+1)` — chỉ số rủi ro diễn đạt có trọng số volume. **Không** phải Shannon entropy.
- **Xử lý tài liệu:** `pdfplumber`, `PyMuPDF`, Tesseract OCR.

### Backend (Python)
- **Framework:** FastAPI (chạy bằng Uvicorn).
- **Task Queue:** Arq + Redis cho các tiến trình cào dữ liệu, xử lý AI ngầm.
- **Data Stack (Database & Storage):**
  - **Neo4j:** Đồ thị tri thức (Knowledge Graph) quản lý quan hệ phức tạp giữa Điều, Khoản, Chủ đề.
  - **Qdrant:** Vector Database phục vụ tìm kiếm ngữ nghĩa (Semantic Search).
  - **PostgreSQL 16:** Lưu metadata (users, jobs, audit, versioning).
  - **Redis:** Queue job & cache truy vấn.
  - **MinIO:** S3-compatible Object Storage lưu file gốc.

### Frontend (TypeScript / React)
- **Kiến trúc Monorepo (Vite):** một app `web` (citizen `/` + admin `/admin`) và shared package `ui-legal`.
- **State Management & UI:** React Router, TailwindCSS; Admin graph canvas dùng `react-force-graph-2d`.

---

## 🚀 Hướng dẫn Cài đặt & Khởi chạy (Local Development)

Dự án cung cấp một script hợp nhất `run.ps1` (trên PowerShell/Windows) hoặc bạn có thể khởi chạy từng phần.

### Yêu cầu hệ thống
- **Python** 3.10+
- **Node.js** **22+** (Vite 8 / Rolldown; Railway FE ghim Node 22)
- **Docker & Docker Compose**
- **OpenAI-compatible API** cho chat + embedding (không dùng Ollama). Copy `Backend/.env.example` → `Backend/.env` và điền:
  - `BE2_OPENAI_BASE_URL`, `BE2_OPENAI_API_KEY`
  - `BE2_EMBEDDING_MODEL=text-embedding-3-small`, `BE2_EMBEDDING_DIMENSION=1536`
  - (tuỳ chọn) `BE2_EMBEDDING_BASE_URL` / `BE2_EMBEDDING_API_KEY` nếu khác host chat

### Các bước khởi chạy

#### 1. Khởi động Data Stack (Các DB & Storage)
Mở terminal trong thư mục gốc dự án và chạy Docker:
```bash
docker-compose -f Data/docker-compose.data.yml --env-file Data/.env up -d
```
*(Khởi chạy: Postgres, Neo4j, Qdrant, Redis, MinIO).*

> **Qdrant dimension:** schema/seed mặc định dùng vector size **1536**. Nếu collection cũ đang ở 1024, recreate (purge Qdrant hoặc seed lại) trước khi ingest/RAG — lệch dim sẽ lỗi.

> **Production checklist (bắt buộc trước khi công bố):**
> 1. `APP_ENV=production` + `AUTH_TOKEN_SECRET` ≥32 ký tự ngẫu nhiên (không chứa `change-me`) + `ENABLE_DEV_TOKENS=false`
> 2. `BE2_OPENAI_API_KEY` / `BE2_EMBEDDING_API_KEY` **sống suốt cửa sổ demo** (QA/ingest/embedding chết nếu hết credit). Chuẩn bị key dự phòng hoặc quay video fallback.
> 3. `Data/.env` `EMBEDDING_DIM=1536` khớp backend; recreate Qdrant nếu trước đó dùng 1024
> 4. Chạy `cd Backend && pytest -vv` → 0 failed
> 5. **Railway FE:** Root Directory = `Frontend`. **Không** đặt Build Command = `npm ci && …` (Railpack đã install — lần 2 gây EBUSY). Chỉ cần `VITE_API_URL=https://<backend-public>.up.railway.app`, Redeploy. Citizen `/`, Admin `/admin`. Backend: `CORS_ALLOW_ALL=true`.
> 6. **Railway BE:** Root Directory = `Backend`, builder Dockerfile. **Tắt Healthcheck Path trong UI** (hoặc để trống) — dùng TCP port check; HTTP `/health` vẫn có để tự kiểm. `AUTH_TOKEN_SECRET` ≥32 ký tự. BE2 service: Dockerfile path = `Dockerfile.be2`.
> 7. Nếu deploy vẫn **Healthcheck failure**: Settings → Healthcheck → **Clear path** → Redeploy. Kiểm tra Deploy logs có `Uvicorn running on http://0.0.0.0`.

### Git LFS (backup Qdrant / snapshot lớn)

Một số file dưới `Data/backups/` dùng **Git LFS**. Clone thường chỉ thấy pointer text (~130 byte) nếu chưa kéo LFS:

```bash
git lfs install
git lfs pull
```

Không có `git-lfs` thì bỏ qua backup snapshot và dùng seed/reindex thay thế.

### Demo sống (điền URL sau khi deploy)

| Thành phần | URL |
|---|---|
| Frontend (citizen) | `https://<fe>.up.railway.app/` |
| Frontend (admin) | `https://<fe>.up.railway.app/admin/` |
| Backend BE3 docs | `https://<be3>.up.railway.app/docs` |
| Backend BE2 health | `https://<be2>.up.railway.app/health` |

Health tối thiểu trước khi chấm: `GET /health` (BE3) và `GET /health` (BE2, `openai_reachable: true`).

#### 2. Cài đặt Dependency và Khởi chạy Ứng dụng
Sử dụng script PowerShell `run.ps1` để tự động tạo môi trường ảo Python (venv), cài đặt thư viện (`pip`, `npm`), seed dữ liệu mẫu, và bật các services:

```powershell
# Chạy lần đầu tiên (có cài đặt dependency)
./run.ps1 -Install

# Những lần sau chỉ cần chạy
./run.ps1
```

Script này sẽ tự động bật các cửa sổ mới cho **BE3 API (:8000)**, **BE2 LLM gateway (:8002)**, Worker (Arq), và Frontend (Vite).

> **Quan trọng:** QA gọi LLM qua `BE2_INTELLIGENCE_URL` → `be2_service` trên **:8002**, rồi mới tới OpenAI-compatible host (`BE2_OPENAI_BASE_URL`). Nếu chỉ chạy `uvicorn app.main:app --port 8000` mà không chạy BE2, chatbot vẫn có thể trả lời bằng principle-fallback cục bộ — **không có request nào tới 9router**. Kiểm tra: `curl http://localhost:8002/health` → `"openai_reachable": true`.

Không dùng `run.ps1` thì mở **hai** terminal Backend:

```powershell
# Terminal A — BE2 gateway (bắt buộc cho LLM thật)
cd Backend
.\.venv\Scripts\Activate.ps1
uvicorn be2_service:app --port 8002 --reload

# Terminal B — BE3 API
cd Backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --port 8000 --reload
```

#### 3. Truy cập Hệ thống
Sau khi khởi chạy thành công, bạn có thể truy cập qua các địa chỉ sau:

- **Frontend (citizen):** [http://localhost:5173/](http://localhost:5173/)
  - Truy cập công khai, không cần đăng nhập.
- **Frontend (admin):** [http://localhost:5173/admin/](http://localhost:5173/admin/)
  - Tài khoản kiểm thử: `admin@local` / `admin123`
- **Backend API (FastAPI Docs):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Backend Gateway:** [http://localhost:8002/health](http://localhost:8002/health)

#### 4. Dừng Hệ thống
Để tắt tất cả các app đang chạy (trừ Docker):
```powershell
./run.ps1 -Stop
```
Để tắt Docker, dùng lệnh `docker-compose down`.

---

## 🧪 Tài liệu Kỹ thuật & Kiểm thử

- **Cấu trúc dữ liệu & Lược đồ đồ thị:** Xem chi tiết trong thư mục `Data/schema/`. 
- **Kiểm thử (Testing):** Dự án sử dụng `pytest`. Trong venv Backend, cài dependency rồi chạy:
  ```powershell
  cd Backend
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  $env:PYTHONPATH = "."
  $env:ENABLE_DEV_TOKENS = "1"
  $env:APP_ENV = "local"
  $env:AUTH_TOKEN_SECRET = "test-auth-token-secret-at-least-32-chars"
  pytest -vv
  ```
---

## 👥 Đội ngũ (CMC 404 Not Found)

- **Backend 1 (Legal Pipeline):** Xử lý văn bản luật, NER, Graph Construction.
- **Backend 2 (Social Pipeline):** Giám sát MXH, Topic Classification, NLI, LLM Router.
- **Backend 3 (API Core):** API Gateway, RAG Engine, RBAC Auth.
- **Frontend (Dual Portal):** Giao diện UI/UX tối ưu cho cả Admin & Người dân.
- **Database (Data Platform):** Thiết kế mô hình Neo4j/Qdrant, Seed data & Quản lý Lineage.

---
*Bản quyền © 2026 - Phát triển bởi đội ngũ CMC 404 Not Found.*

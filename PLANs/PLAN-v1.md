# LexSocial AI — Implementation Plan v1
> **Tagline:** Đồ thị tri thức pháp luật - Giải mã quy định, Minh bạch thông tin đại chúng.
> **Base:** Fork từ [open-notebook](https://github.com/lfnovo/open-notebook) (v1.13.0)
> **Deadline:** 48h Hackathon

---

## 1. Chiến lược tổng quan: Fork & Extend

Open-notebook đã có sẵn:
- ✅ FastAPI backend (port 5055) + SurrealDB (port 8000) + Next.js frontend (port 3000/8502)
- ✅ LangGraph workflows (chat, ask, source processing, transformation)
- ✅ Multi-provider AI (OpenAI, Anthropic, Google, Groq, Ollama…)
- ✅ Vector search + Full-text search + Embeddings
- ✅ Docker deployment (docker-compose.yml)
- ✅ Job queue (Surreal-Commands worker)

**Chiến lược:** KHÔNG xây lại từ đầu. Fork open-notebook → thêm 4 module LexSocial lên trên.

---

## 2. Mapping 4 Module → Open-Notebook Architecture

### Module 1: Legal Parser (Bóc tách Pháp luật)
**Tận dụng:** Source Processing workflow (`open_notebook/graphs/source.py`)
**Cần thêm:**
- Custom `LegalParserGraph` — LangGraph workflow mới trong `open_notebook/graphs/legal_parser.py`
- Prompt template mới trong `prompts/legal_parser/` để LLM bóc tách Điều–Khoản–Điểm
- NER prompt để gắn nhãn: Chủ thể, Nghĩa vụ, Quyền lợi, Hành vi cấm, Thời hạn, Hình phạt
- Domain model mới: `LegalArticle`, `LegalClause`, `LegalPoint` trong `open_notebook/domain/legal.py`
- API endpoints: `POST /api/legal/parse`, `GET /api/legal/articles`
- SurrealDB migration cho tables: `legal_article`, `legal_clause`, `legal_point`

### Module 2: Social Media Linker (Radar MXH)
**Tận dụng:** Source ingestion + Transformation workflow
**Cần thêm:**
- Mock data: 50 bài post Facebook/TikTok (JSON) trong `data/mock_social_posts.json`
- Domain model: `SocialPost` với fields: platform, content, author, engagement, timestamp
- `SocialLinkerGraph` — LangGraph workflow đọc post → bóc tách Claim → tạo Edge trỏ đến `legal_article`
- API: `POST /api/social/import`, `GET /api/social/posts`, `GET /api/social/links`
- SurrealDB tables: `social_post`, edge table `discusses` (social_post → legal_article)

### Module 3: Misinformation Detector (Bộ lọc Tin sai)
**Tận dụng:** Ask workflow pattern + Transformation workflow
**Cần thêm:**
- `MisinfoDetectorGraph` — LangGraph đối chiếu Claim vs Legal Facts
- Prompt template cho fact-checking trong `prompts/misinfo_detector/`
- Output: flag (GREEN/RED), explanation, correction text, confidence score
- Domain model: `MisinfoResult` với status, explanation, referenced_articles
- API: `POST /api/misinfo/check`, `GET /api/misinfo/dashboard`
- SurrealDB table: `misinfo_result`

### Module 4: Analytics Dashboard & Q&A
**Tận dụng:** Chat workflow + Search + Frontend
**Cần thêm:**
- Frontend pages mới trong `frontend/src/app/`:
  - `/dashboard` — Top điều luật bị hiểu sai, thống kê tổng quan
  - `/graph` — Visualize Knowledge Graph (SurrealDB graph)
  - `/qa` — Chat Q&A với trích dẫn nguồn luật
  - `/social` — Feed bài post MXH với flag xanh/đỏ
- API aggregation endpoints: `GET /api/analytics/top-misinfo`, `GET /api/analytics/stats`
- Chart library: Recharts (Next.js ecosystem)
- Graph visualization: `react-force-graph` hoặc `d3-force`

---

## 3. Phân chia công việc theo đội

### Đội AI (Dũng, An) — Module 1 + 3
| Task | File/Location | Priority |
|------|--------------|----------|
| Schema LegalArticle/Clause/Point | `open_notebook/domain/legal.py` | P0 |
| Legal Parser prompt | `prompts/legal_parser/system.md` | P0 |
| NER extraction prompt | `prompts/legal_parser/ner.md` | P0 |
| LegalParserGraph | `open_notebook/graphs/legal_parser.py` | P0 |
| MisinfoDetector prompt | `prompts/misinfo_detector/system.md` | P0 |
| MisinfoDetectorGraph | `open_notebook/graphs/misinfo_detector.py` | P1 |
| SocialLinkerGraph | `open_notebook/graphs/social_linker.py` | P1 |

### Đội Backend (Quốc An, Tùng, Cường) — Infra + API
| Task | File/Location | Priority |
|------|--------------|----------|
| Fork repo, setup Docker | docker-compose.yml | P0 |
| DB migrations (legal tables) | `open_notebook/database/migrations/` | P0 |
| API routes: legal parser | `api/routers/legal.py` | P0 |
| API routes: social posts | `api/routers/social.py` | P1 |
| API routes: misinfo | `api/routers/misinfo.py` | P1 |
| API routes: analytics | `api/routers/analytics.py` | P1 |
| Mock data seeder script | `scripts/seed_mock_data.py` | P1 |
| Deploy server (public URL) | CI/CD | P0 — DL: Thứ 7, 23:00 |

### Đội Frontend (Lê Dương, Quang Anh) — Dashboard + UI
| Task | File/Location | Priority |
|------|--------------|----------|
| Layout Dashboard page | `frontend/src/app/dashboard/` | P0 |
| Graph visualization component | `frontend/src/components/legal-graph/` | P1 |
| Social feed page | `frontend/src/app/social/` | P1 |
| Q&A chat page (reuse chat) | `frontend/src/app/qa/` | P1 |
| Misinfo flag badges (🟢🔴) | `frontend/src/components/misinfo-badge/` | P2 |
| Recharts integration | `frontend/src/components/charts/` | P1 |

---

## 4. Timeline 48h

| Giờ | Milestone |
|-----|-----------|
| 0–4h | Fork repo, Docker up, DB migrations, domain models |
| 4–12h | Legal Parser graph + prompt + API hoàn chỉnh |
| 12–20h | Social Linker + Mock data + Misinfo Detector |
| 20–30h | Frontend Dashboard + Graph viz + Q&A chat |
| 30–40h | Integration test, fix bugs, polish UI |
| 40–46h | Deploy public, demo prep |
| 46–48h | Buffer + final demo |

---

## 5. ⚠️ CÂU HỎI CẦN ANH QUYẾT ĐỊNH

### Q1: Database — SurrealDB hay Neo4j?
Đề bài ghi dùng Neo4j. Open-notebook dùng SurrealDB (cũng hỗ trợ graph + vector).

| Phương án | Ưu | Nhược |
|-----------|-----|-------|
| **A) Giữ SurrealDB** | Không cần thêm infra, tận dụng 100% code | Không đúng đề bài "Neo4j" |
| **B) Thêm Neo4j song song** | Đúng đề bài, viz mạnh | Phức tạp, thêm Docker service, sync 2 DB |
| **C) Thay SurrealDB = Neo4j** | Đúng đề hoàn toàn | Rewrite data layer → KHÔNG KHẢ THI 48h |

**Đề xuất:** A — giữ SurrealDB. Graph viz dùng `react-force-graph`.

### Q2: Vector DB — Riêng hay dùng SurrealDB?
Đề bài ghi Qdrant/Milvus. SurrealDB đã có built-in vector search.

**Đề xuất:** Dùng luôn SurrealDB vector search. Không thêm Qdrant/Milvus.

### Q3: LLM Provider nào?
- **GPT-4o** — Ổn định, tiếng Việt tốt
- **Gemini** — Free tier rộng
- **Claude** — Reasoning mạnh
- **Groq (Llama)** — Free, nhanh, tiếng Việt yếu

**Đề xuất:** GPT-4o hoặc Gemini (tùy API key có sẵn).

### Q4: Dữ liệu pháp luật mẫu?
- **A)** Luật An ninh mạng 2018 (hot topic)
- **B)** Luật Giao thông đường bộ (dễ hiểu)
- **C)** Nghị định xử phạt hành chính (dễ verify đúng/sai)
- **D)** Luật khác?

### Q5: Frontend — Extend hay Custom?
- **A) Extend:** Thêm pages vào frontend có sẵn (nhanh)
- **B) Custom:** Layout riêng bằng Tailwind (đẹp hơn, tốn thời gian hơn)

**Đề xuất:** A — extend open-notebook, custom branding lên trên.

### Q6: Tên repo Github public?

### Q7: Ảnh đề bài?
Anh đề cập "đề bài như ảnh" — tôi chưa nhận được ảnh. Share lại được không?

---

## 6. Tech Stack tổng kết

| Layer | Technology | Source |
|-------|-----------|--------|
| Frontend | Next.js 15 + React 19 + TypeScript + Tailwind + Shadcn/ui | open-notebook |
| Charts | Recharts | Thêm mới |
| Graph Viz | react-force-graph / d3-force | Thêm mới |
| Backend | Python 3.11+ + FastAPI | open-notebook |
| AI Workflows | LangGraph + Esperanto | open-notebook |
| LLM | GPT-4o / Gemini (TBD) | Config |
| Database | SurrealDB (graph + vector + relational) | open-notebook |
| Job Queue | Surreal-Commands worker | open-notebook |
| Deploy | Docker Compose | open-notebook |

---

## 7. Rủi ro & Mitigation

| Rủi ro | Impact | Mitigation |
|--------|--------|-----------|
| Prompt tiếng Việt kém | Bóc tách sai | Test sớm, few-shot examples |
| SurrealDB graph viz hạn chế | Demo kém ấn tượng | react-force-graph render trên FE |
| Deploy chậm | Trễ deadline Thứ 7 | Dockerize sớm, deploy ngày đầu |
| Mock data không thực tế | BGK thấy giả | Crawl thật 20-30 bài Facebook |
| LLM rate limit | API bị block | Cache responses, batch processing |

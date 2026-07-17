# LexSocial AI — Implementation Plan v2 (Final)

> **Tagline:** Đồ thị tri thức pháp luật — Giải mã quy định, Minh bạch thông tin đại chúng
> **Repo:** https://github.com/antondung/CMC-404-Not-Found
> **Base:** Fork từ [open-notebook](https://github.com/lfnovo/open-notebook) v1.13.0
> **Deadline:** 48h Hackathon
> **Đội:** CMC 404 Not Found

---

## 0. Quyết định kiến trúc (đã chốt)

| Câu hỏi | Quyết định | Lý do |
|----------|-----------|-------|
| Database | **SurrealDB** (giữ nguyên) | Đã có graph + vector + relational. Đề bài yêu cầu "knowledge graph" — không bắt buộc Neo4j. SurrealDB graph queries (`RELATE`, `->`, `<-`) đủ mạnh cho demo |
| Vector DB | **SurrealDB built-in** | Không thêm Qdrant/Milvus. Giảm infra complexity |
| LLM Provider | **Google Gemini 2.5 Flash** (primary) + **GPT-4o** (fallback) | Gemini: free tier rộng, tiếng Việt tốt, context 1M tokens. GPT-4o: backup nếu Gemini rate limit |
| Dữ liệu pháp luật | **Các luật có hiệu lực từ 01/07/2026** | Đúng context đề bài. VD: Luật Đất đai 2024, Luật Nhà ở 2023, Luật KDBĐS 2023, Luật Căn cước 2023, Luật Viễn thông 2023... |
| Frontend | **Custom lại frontend** open-notebook | User yêu cầu rõ ràng. Giữ Next.js + Shadcn/ui framework, redesign layout + pages cho LexSocial theme |
| Tên repo | `CMC-404-Not-Found` | Đã có sẵn |

---

## 1. Chiến lược: Fork → Rebrand → Extend

```
open-notebook (base)
    │
    ├── GIỮ NGUYÊN (không sửa)
    │   ├── SurrealDB connection + migrations framework
    │   ├── Esperanto AI provider layer
    │   ├── LangGraph engine
    │   ├── FastAPI core + middleware
    │   ├── Docker Compose infra
    │   └── Surreal-Commands worker
    │
    ├── SỬA / MỞ RỘNG
    │   ├── Database migrations → thêm tables cho legal/social/misinfo
    │   ├── Domain models → thêm LegalArticle, SocialPost, MisinfoResult
    │   ├── Graphs → thêm 3 LangGraph workflows mới
    │   ├── API routers → thêm 4 router modules mới
    │   └── Prompts → thêm prompt templates tiếng Việt
    │
    └── CUSTOM HOÀN TOÀN
        └── Frontend → Redesign cho LexSocial AI theme
            ├── Dashboard (thống kê, top misinfo)
            ├── Knowledge Graph viewer
            ├── Social Media feed + misinfo flags
            └── Q&A Chat với trích dẫn luật
```

---

## 2. Data Model — SurrealDB Schema

### 2.1 Legal Document Tables

```sql
-- Văn bản pháp luật (Luật, Nghị định, Thông tư)
DEFINE TABLE legal_document SCHEMAFULL;
DEFINE FIELD doc_number    ON legal_document TYPE string;    -- "13/2023/QH15"
DEFINE FIELD doc_type      ON legal_document TYPE string;    -- "Luật" | "Nghị định" | "Thông tư"
DEFINE FIELD title         ON legal_document TYPE string;    -- "Luật Đất đai"
DEFINE FIELD issued_date   ON legal_document TYPE datetime;
DEFINE FIELD effective_date ON legal_document TYPE datetime;
DEFINE FIELD issuer        ON legal_document TYPE string;    -- "Quốc hội"
DEFINE FIELD status        ON legal_document TYPE string;    -- "active" | "amended" | "repealed"
DEFINE FIELD full_text     ON legal_document TYPE string;
DEFINE FIELD created       ON legal_document TYPE datetime DEFAULT time::now();
DEFINE FIELD updated       ON legal_document TYPE datetime DEFAULT time::now();

-- Điều (Article)
DEFINE TABLE legal_article SCHEMAFULL;
DEFINE FIELD document      ON legal_article TYPE record<legal_document>;
DEFINE FIELD article_number ON legal_article TYPE int;
DEFINE FIELD title         ON legal_article TYPE string;
DEFINE FIELD content       ON legal_article TYPE string;
DEFINE FIELD created       ON legal_article TYPE datetime DEFAULT time::now();

-- Khoản (Clause)
DEFINE TABLE legal_clause SCHEMAFULL;
DEFINE FIELD article       ON legal_clause TYPE record<legal_article>;
DEFINE FIELD clause_number ON legal_clause TYPE int;
DEFINE FIELD content       ON legal_clause TYPE string;
DEFINE FIELD created       ON legal_clause TYPE datetime DEFAULT time::now();

-- Điểm (Point)
DEFINE TABLE legal_point SCHEMAFULL;
DEFINE FIELD clause        ON legal_point TYPE record<legal_clause>;
DEFINE FIELD point_label   ON legal_point TYPE string;       -- "a", "b", "c"...
DEFINE FIELD content       ON legal_point TYPE string;
DEFINE FIELD created       ON legal_point TYPE datetime DEFAULT time::now();

-- NER Entities bóc tách từ mỗi điều/khoản/điểm
DEFINE TABLE legal_entity SCHEMAFULL;
DEFINE FIELD source_ref    ON legal_entity TYPE string;      -- record ID of article/clause/point
DEFINE FIELD entity_type   ON legal_entity TYPE string;      -- "subject" | "obligation" | "right" | "prohibition" | "deadline" | "penalty" | "related_doc"
DEFINE FIELD value         ON legal_entity TYPE string;
DEFINE FIELD created       ON legal_entity TYPE datetime DEFAULT time::now();

-- Theo dõi sửa đổi (Amendment tracking)
DEFINE TABLE amends SCHEMAFULL;                              -- Edge: new_doc -> old_doc
DEFINE FIELD in            ON amends TYPE record<legal_document>;
DEFINE FIELD out           ON amends TYPE record<legal_document>;
DEFINE FIELD change_type   ON amends TYPE string;            -- "replaces" | "amends" | "supplements"
DEFINE FIELD summary       ON amends TYPE string;
DEFINE FIELD created       ON amends TYPE datetime DEFAULT time::now();
```

### 2.2 Social Media Tables

```sql
-- Bài post MXH
DEFINE TABLE social_post SCHEMAFULL;
DEFINE FIELD platform      ON social_post TYPE string;       -- "facebook" | "tiktok" | "twitter"
DEFINE FIELD author         ON social_post TYPE string;
DEFINE FIELD content        ON social_post TYPE string;
DEFINE FIELD url            ON social_post TYPE option<string>;
DEFINE FIELD posted_at      ON social_post TYPE datetime;
DEFINE FIELD likes          ON social_post TYPE int DEFAULT 0;
DEFINE FIELD comments       ON social_post TYPE int DEFAULT 0;
DEFINE FIELD shares         ON social_post TYPE int DEFAULT 0;
DEFINE FIELD created        ON social_post TYPE datetime DEFAULT time::now();

-- Claim bóc tách từ bài post
DEFINE TABLE social_claim SCHEMAFULL;
DEFINE FIELD post           ON social_claim TYPE record<social_post>;
DEFINE FIELD claim_text     ON social_claim TYPE string;
DEFINE FIELD sentiment      ON social_claim TYPE string;     -- "positive" | "negative" | "neutral"
DEFINE FIELD created        ON social_claim TYPE datetime DEFAULT time::now();

-- Edge: claim -> legal_article (liên kết)
DEFINE TABLE discusses SCHEMAFULL;
DEFINE FIELD in             ON discusses TYPE record<legal_article>;
DEFINE FIELD out            ON discusses TYPE record<social_claim>;
DEFINE FIELD relevance      ON discusses TYPE float;          -- 0.0 - 1.0
DEFINE FIELD created        ON discusses TYPE datetime DEFAULT time::now();
```

### 2.3 Misinformation Tables

```sql
-- Kết quả fact-check
DEFINE TABLE misinfo_result SCHEMAFULL;
DEFINE FIELD claim          ON misinfo_result TYPE record<social_claim>;
DEFINE FIELD status         ON misinfo_result TYPE string;   -- "accurate" | "misleading" | "false"
DEFINE FIELD flag           ON misinfo_result TYPE string;   -- "green" | "yellow" | "red"
DEFINE FIELD explanation    ON misinfo_result TYPE string;
DEFINE FIELD correction     ON misinfo_result TYPE option<string>;
DEFINE FIELD confidence     ON misinfo_result TYPE float;
DEFINE FIELD legal_refs     ON misinfo_result TYPE array;    -- [record IDs of articles]
DEFINE FIELD created        ON misinfo_result TYPE datetime DEFAULT time::now();
```

### 2.4 Graph Relationships (Visual)

```
legal_document ──has_article──→ legal_article
legal_article  ──has_clause──→  legal_clause
legal_clause   ──has_point──→   legal_point
legal_article  ←──discusses──   social_claim
social_claim   ←──from_post──   social_post
social_claim   ──checked_by──→  misinfo_result
legal_document ──amends──→      legal_document (old)
```

---

## 3. LangGraph Workflows (3 mới)

### 3.1 LegalParserGraph (`open_notebook/graphs/legal_parser.py`)

```
Input: Raw legal text (PDF/paste)
  ↓
Step 1: Structure Parser
  → LLM chặt nhỏ thành Điều → Khoản → Điểm (JSON output)
  ↓
Step 2: NER Extractor
  → Với mỗi đơn vị, LLM gắn nhãn entities
  → (subject, obligation, right, prohibition, deadline, penalty, related_doc)
  ↓
Step 3: Amendment Detector
  → So sánh với docs cũ trong DB, phát hiện thay đổi
  ↓
Step 4: Embed & Save
  → Tạo embeddings cho từng chunk
  → Lưu tất cả vào SurrealDB
  ↓
Output: Structured legal data + graph edges
```

### 3.2 SocialLinkerGraph (`open_notebook/graphs/social_linker.py`)

```
Input: Social post content
  ↓
Step 1: Claim Extractor
  → LLM bóc tách các luận điểm/tuyên bố pháp lý
  ↓
Step 2: Legal Matcher
  → Vector search + keyword match tìm Điều/Khoản liên quan
  → Tạo edges (discusses) trong SurrealDB
  ↓
Step 3: Sentiment Analyzer
  → Phân loại cảm xúc/thái độ
  ↓
Output: Claims + graph links + sentiment
```

### 3.3 MisinfoDetectorGraph (`open_notebook/graphs/misinfo_detector.py`)

```
Input: social_claim record
  ↓
Step 1: Retrieve Legal Facts
  → Lấy nội dung Điều/Khoản đã liên kết
  ↓
Step 2: Cross-Reference Check
  → LLM đối chiếu claim vs. legal facts
  → Output: accurate | misleading | false
  ↓
Step 3: Generate Correction
  → Nếu sai: sinh lời giải thích đính chính
  → Kèm trích dẫn nguồn (Điều X, Khoản Y)
  ↓
Output: MisinfoResult (flag + explanation + correction + citations)
```

---

## 4. API Endpoints mới

### 4.1 Legal Router (`api/routers/legal.py`)

```
POST   /api/legal/documents          Upload & parse legal document
GET    /api/legal/documents          List all documents
GET    /api/legal/documents/{id}     Get document with articles
GET    /api/legal/articles           List articles (filterable)
GET    /api/legal/articles/{id}      Get article with clauses, points, entities
GET    /api/legal/entities           Search entities by type
GET    /api/legal/amendments         Get amendment history
POST   /api/legal/parse-text        Parse raw legal text (no file upload)
```

### 4.2 Social Router (`api/routers/social.py`)

```
POST   /api/social/posts             Import posts (batch)
GET    /api/social/posts             List posts with claims
GET    /api/social/posts/{id}        Get post with linked articles
POST   /api/social/analyze           Analyze a single post
GET    /api/social/claims            List all claims with links
GET    /api/social/graph             Get graph data (nodes + edges) for visualization
```

### 4.3 Misinfo Router (`api/routers/misinfo.py`)

```
POST   /api/misinfo/check            Fact-check a claim
GET    /api/misinfo/results          List all results (filterable by flag)
GET    /api/misinfo/results/{id}     Get detailed result with citations
POST   /api/misinfo/batch-check     Batch fact-check multiple claims
```

### 4.4 Analytics Router (`api/routers/analytics.py`)

```
GET    /api/analytics/stats           Overall statistics
GET    /api/analytics/top-misinfo     Top articles with most misinformation
GET    /api/analytics/trends          Discussion trends over time
GET    /api/analytics/graph-data      Full knowledge graph data for visualization
```

---

## 5. Frontend — Custom LexSocial Theme

### 5.1 Page Structure

```
/                        → Landing / redirect to /dashboard
/dashboard               → Main dashboard (stats, charts, top misinfo)
/legal                   → Legal documents list
/legal/[id]              → Document detail (Điều-Khoản-Điểm tree)
/social                  → Social media feed with flags
/social/[id]             → Post detail with linked articles
/graph                   → Interactive Knowledge Graph visualization
/qa                      → Q&A Chat (reuse open-notebook chat, rethemed)
```

### 5.2 Key Components

```
frontend/src/
├── app/
│   ├── layout.tsx                → LexSocial theme wrapper + nav
│   ├── dashboard/page.tsx        → Stats cards + charts + top misinfo table
│   ├── legal/
│   │   ├── page.tsx              → Document list with search/filter
│   │   └── [id]/page.tsx         → Hierachical Điều-Khoản-Điểm viewer
│   ├── social/
│   │   ├── page.tsx              → Post feed with 🟢🟡🔴 badges
│   │   └── [id]/page.tsx         → Post detail + linked articles
│   ├── graph/page.tsx            → react-force-graph viz
│   └── qa/page.tsx               → Chat interface with citations
├── components/
│   ├── lexsocial/
│   │   ├── nav-sidebar.tsx       → Custom navigation
│   │   ├── stat-card.tsx         → Dashboard stat cards
│   │   ├── misinfo-badge.tsx     → 🟢🟡🔴 flag badges
│   │   ├── legal-tree.tsx        → Collapsible Điều-Khoản-Điểm tree
│   │   ├── entity-tags.tsx       → NER entity tags (colored chips)
│   │   ├── knowledge-graph.tsx   → Force-directed graph viz
│   │   ├── post-card.tsx         → Social post card
│   │   ├── citation-block.tsx    → Source citation display
│   │   └── trend-chart.tsx       → Recharts trend visualization
│   └── ui/                       → Shadcn/ui (giữ nguyên)
```

### 5.3 Design System

```
Branding:
  Primary: #1E3A5F (Navy blue — legal authority)
  Accent:  #22C55E (Green — verified/safe)
  Warning: #F59E0B (Amber — needs attention)
  Danger:  #EF4444 (Red — misinformation)
  BG:      #0F172A (Dark slate — modern dark theme)

Font: Inter (headings) + Roboto Mono (legal text / citations)

Misinfo Flags:
  🟢 Green  → Chính xác (Accurate)
  🟡 Yellow → Gây hiểu lầm (Misleading)
  🔴 Red    → Sai lệch (False/Misinformation)
```

---

## 6. Prompt Templates (tiếng Việt)

### 6.1 Legal Parser — Structure (`prompts/legal_parser/structure.md`)

Core logic: Nhận raw text → output JSON cấu trúc Điều-Khoản-Điểm

### 6.2 Legal Parser — NER (`prompts/legal_parser/ner.md`)

Core logic: Nhận text 1 điều/khoản → gắn nhãn entities

### 6.3 Social Linker — Claim Extraction (`prompts/social_linker/claim.md`)

Core logic: Đọc bài post MXH → bóc tách luận điểm pháp lý

### 6.4 Misinfo Detector — Fact Check (`prompts/misinfo_detector/factcheck.md`)

Core logic: So sánh claim vs. legal facts → phán định đúng/sai + giải thích

*(Chi tiết prompt sẽ viết trong phase implementation)*

---

## 7. Dữ liệu

### 7.1 Văn bản pháp luật — DO TEAM CUNG CẤP

> **Ngày hiệu lực:** 01/07/2026 (July 1, 2026)
> **Nguồn:** Anh Dũng sẽ upload toàn bộ văn bản luật, nghị định, thông tư mới.

- Hệ thống cần hỗ trợ import nhiều định dạng: **PDF, DOCX, plain text**
- Legal Parser sẽ tự động bóc tách cấu trúc Điều–Khoản–Điểm từ văn bản được upload
- **KHÔNG hardcode** nội dung luật vào code — mọi dữ liệu đều qua API upload
- Backend cần endpoint bulk import: `POST /api/legal/documents/bulk`

**Workflow khi nhận luật:**
1. Anh upload file(s) → API nhận → lưu raw text
2. LegalParserGraph chạy async → bóc tách cấu trúc + NER
3. Embeddings tự động tạo → sẵn sàng search
4. Frontend hiển thị kết quả parse ngay

### 7.2 Social Posts (50 posts mock — team tự tạo)

- Mock data sẽ được tạo **SAU KHI** có nội dung luật thật
- Dựa trên nội dung luật thật để viết posts giả lập cho thực tế
- AI team sẽ dùng LLM generate 50 posts dựa trên các Điều/Khoản hot
- Mix: 60% sai/hiểu lầm, 25% chính xác, 15% gây hiểu lầm
- Format: JSON array, import qua `POST /api/social/posts` (batch)

---

## 8. Phân công chi tiết theo đội

### Đội AI (Dũng, An)

| # | Task | Output | Giờ |
|---|------|--------|-----|
| 1 | Legal Parser prompt + few-shot examples | `prompts/legal_parser/*.md` | 0-4h |
| 2 | LegalParserGraph workflow | `open_notebook/graphs/legal_parser.py` | 4-10h |
| 3 | Test parser với 1 văn bản luật thật | Verified output | 10-12h |
| 4 | Social Linker prompt + graph | `prompts/social_linker/`, graph file | 12-18h |
| 5 | Misinfo Detector prompt + graph | `prompts/misinfo_detector/`, graph file | 18-24h |
| 6 | Tạo mock social posts (50 posts) | `data/mock_social_posts.json` | 24-28h |
| 7 | End-to-end pipeline test | All graphs working | 28-32h |

### Đội Backend (Quốc An, Tùng, Cường)

| # | Task | Output | Giờ |
|---|------|--------|-----|
| 1 | Fork repo, Docker up, verify base works | Running system | 0-2h |
| 2 | SurrealDB migration (legal + social + misinfo tables) | Migration files | 2-6h |
| 3 | Domain models (legal.py, social.py, misinfo.py) | `open_notebook/domain/` | 2-6h |
| 4 | Legal API router | `api/routers/legal.py` | 6-14h |
| 5 | Social API router | `api/routers/social.py` | 14-20h |
| 6 | Misinfo API router | `api/routers/misinfo.py` | 20-26h |
| 7 | Analytics API router | `api/routers/analytics.py` | 26-30h |
| 8 | Seed mock data script | `scripts/seed_data.py` | 30-34h |
| 9 | **Deploy server (public URL)** | Live URL | **34-38h (DL: Thứ 7 23:00)** |
| 10 | Bug fixes + integration | Stable API | 38-46h |

### Đội Frontend (Lê Dương, Quang Anh)

| # | Task | Output | Giờ |
|---|------|--------|-----|
| 1 | Setup LexSocial theme (colors, fonts, layout) | Theme files | 0-4h |
| 2 | Navigation sidebar component | `nav-sidebar.tsx` | 4-6h |
| 3 | Dashboard page (stat cards + placeholders) | `/dashboard` | 6-12h |
| 4 | Legal document list + detail page | `/legal`, `/legal/[id]` | 12-20h |
| 5 | Recharts integration (trends, stats) | Chart components | 20-26h |
| 6 | Knowledge Graph visualization | `/graph` page | 26-32h |
| 7 | Social feed page + misinfo badges | `/social` | 32-36h |
| 8 | Q&A Chat page (reuse chat component) | `/qa` | 36-40h |
| 9 | Connect all pages to real API | API integration | 40-44h |
| 10 | Polish, responsive, demo-ready | Final UI | 44-48h |

---

## 9. Timeline tổng hợp 48h

```
Hour  0 ─────── 8 ─────── 16 ─────── 24 ─────── 32 ─────── 40 ─────── 48
      │         │          │          │          │          │          │
AI:   [Prompts+Parser]────[Social+Misinfo]─────[Mock data+E2E test]──[Support]
BE:   [Fork+DB+Models]────[Legal API]──[Social+Misinfo API]──[Deploy]─[Fix]
FE:   [Theme+Layout]──────[Dashboard+Legal]────[Graph+Social]──[QA+Polish]
      │                                                    │
      ▼                                                    ▼
   Kickoff                                         Deploy DL (Sat 23:00)
```

---

## 10. Rủi ro & Mitigation

| # | Rủi ro | Xác suất | Impact | Mitigation |
|---|--------|---------|--------|-----------|
| 1 | LLM parse sai cấu trúc luật VN | Cao | Cao | Few-shot examples trong prompt; test sớm; fallback parse bằng regex |
| 2 | SurrealDB graph viz thiếu | Trung bình | Trung bình | react-force-graph trên frontend render đẹp |
| 3 | Deploy chậm | Trung bình | Cao | Docker-compose deploy ngay ngày 1; dùng Railway/Render nếu server riêng chậm |
| 4 | Gemini rate limit | Thấp | Cao | Fallback GPT-4o; cache responses |
| 5 | Frontend chưa connect kịp API | Trung bình | Trung bình | FE dùng mock data JSON trước, swap API sau |
| 6 | Open-notebook codebase breaking changes | Thấp | Cao | Pin version v1.13.0, không pull mới |

---

## 11. Deploy Strategy

```yaml
# docker-compose.prod.yml (thêm vào)
services:
  surrealdb:
    # Giữ nguyên từ base
  
  lexsocial-api:
    build: .
    ports:
      - "5055:5055"
    environment:
      - OPEN_NOTEBOOK_ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - SURREAL_URL=ws://surrealdb:8000/rpc
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}    # Gemini
      - OPENAI_API_KEY=${OPENAI_API_KEY}    # Fallback
    depends_on:
      - surrealdb

  lexsocial-frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - API_URL=http://lexsocial-api:5055
    depends_on:
      - lexsocial-api
```

**Deploy targets (ưu tiên):**
1. Railway (free tier, Docker deploy nhanh)
2. Render (alternative)
3. VPS riêng nếu có

---

## 12. Demo Script (2-3 phút)

1. **Upload luật** → Show Legal Parser bóc tách Điều-Khoản-Điểm tự động
2. **Dashboard** → Show thống kê, top điều luật bị hiểu sai
3. **Knowledge Graph** → Zoom vào graph, show connections
4. **Social Feed** → Show bài post với 🟢🟡🔴 flags
5. **Click 🔴 post** → Show correction + trích dẫn nguồn luật
6. **Q&A** → Hỏi "Phạt bao nhiêu khi vượt đèn đỏ?" → Trả lời + citation

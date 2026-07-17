# LexSocial AI — PLAN v3 (FINAL)

> **Tagline:** Đồ thị tri thức pháp luật — Giải mã quy định, Minh bạch thông tin đại chúng
> **Repo:** https://github.com/antondung/CMC-404-Not-Found
> **Base:** Fork từ open-notebook v1.13.0
> **Deadline:** 48h Hackathon | **Đội:** CMC 404 Not Found

---

## 0. Bản chất bài toán

Hệ thống **hợp nhất 2 miền dữ liệu** — văn bản pháp luật (cấu trúc) và dư luận MXH (phi cấu trúc) — qua **Knowledge Graph**, phục vụ: **Q&A có trích dẫn** và **cảnh báo rủi ro truyền thông**.

**Nút thắt lớn nhất:** Ánh xạ ngôn ngữ đời thường ↔ ngôn ngữ pháp lý (Yêu cầu #5).

---

## 1. Ma trận 7 yêu cầu → Module → MVP

| # | Yêu cầu | Module | Độ khó | MVP? |
|---|---------|--------|--------|------|
| 1 | Cấu trúc hóa Điều–Khoản–Điểm | M1: Legal Parser (Regex + LLM fallback) | TB | ✅ |
| 2 | Trích xuất chủ thể/nghĩa vụ/chế tài | M2: Legal NER (LLM few-shot JSON) | Cao | ✅ |
| 3 | Theo dõi thảo luận MXH | M3: Social Monitor (topic classification) | TB | Mở rộng |
| 4 | Thay đổi vs văn bản cũ | M4: Version Diff (regex + semantic diff) | Cao | ✅ |
| 5 | Liên kết bài đăng ↔ quy định | M5: Entity Linker (vector + LLM re-rank) | Rất cao | Demo nhỏ |
| 6 | Phát hiện hiểu lầm/tin sai | M6: Misinfo Detector (NLI) | Rất cao | Demo nhỏ |
| 7 | Dashboard/Q&A có trích dẫn | M7: RAG Q&A + Dashboard | Cao | ✅ |

**Lõi (24h đầu):** M1+M2+M4+M7 → KG pháp luật + Q&A trích dẫn
**Mở rộng (24h sau):** M3+M5+M6 → Social + Link + Misinfo (demo 1-2 chủ đề)

---

## 2. Kiến trúc chốt

| Quyết định | Phương án |
|-----------|----------|
| Database | SurrealDB (graph + vector + relational) |
| LLM | Gemini 2.5 Flash + GPT-4o fallback |
| AI Architecture | LightRAG-inspired (Entity/Rel extraction + Hybrid Search) |
| Frontend | Custom Next.js + Shadcn/ui |
| Dữ liệu | VB hiệu lực 01/07/2026, team upload qua API |

---

## 3. Ontology & SurrealDB Schema

**Nodes:** VanBan → Dieu → Khoan → Diem | ThucThe (7 loại NER) | BaiDang → LuanDiem
**Edges:** thuoc, quy_dinh, ap_dung_cho, thay_the/sua_doi, thao_luan_ve, can_kiem_chung

```sql
-- LEGAL
DEFINE TABLE van_ban SCHEMAFULL;
DEFINE FIELD so_hieu ON van_ban TYPE string;
DEFINE FIELD loai ON van_ban TYPE string;
DEFINE FIELD ten ON van_ban TYPE string;
DEFINE FIELD ngay_hieu_luc ON van_ban TYPE datetime;
DEFINE FIELD co_quan ON van_ban TYPE string;
DEFINE FIELD trang_thai ON van_ban TYPE string;
DEFINE FIELD full_text ON van_ban TYPE string;

DEFINE TABLE dieu SCHEMAFULL;
DEFINE FIELD van_ban ON dieu TYPE record<van_ban>;
DEFINE FIELD so_dieu ON dieu TYPE int;
DEFINE FIELD tieu_de ON dieu TYPE option<string>;
DEFINE FIELD noi_dung ON dieu TYPE string;

DEFINE TABLE khoan SCHEMAFULL;
DEFINE FIELD dieu ON khoan TYPE record<dieu>;
DEFINE FIELD so_khoan ON khoan TYPE int;
DEFINE FIELD noi_dung ON khoan TYPE string;

DEFINE TABLE diem SCHEMAFULL;
DEFINE FIELD khoan ON diem TYPE record<khoan>;
DEFINE FIELD ky_hieu ON diem TYPE string;
DEFINE FIELD noi_dung ON diem TYPE string;

-- NER ENTITIES
DEFINE TABLE thuc_the SCHEMAFULL;
DEFINE FIELD nguon ON thuc_the TYPE string;
DEFINE FIELD loai_thuc_the ON thuc_the TYPE string;
DEFINE FIELD gia_tri ON thuc_the TYPE string;

-- VERSION DIFF EDGES
DEFINE TABLE sua_doi SCHEMAFULL;
DEFINE FIELD in ON sua_doi TYPE record<van_ban>;
DEFINE FIELD out ON sua_doi TYPE record<van_ban>;
DEFINE FIELD kieu ON sua_doi TYPE string;
DEFINE FIELD tom_tat ON sua_doi TYPE string;

-- SOCIAL
DEFINE TABLE bai_dang SCHEMAFULL;
DEFINE FIELD nen_tang ON bai_dang TYPE string;
DEFINE FIELD tac_gia ON bai_dang TYPE string;
DEFINE FIELD noi_dung ON bai_dang TYPE string;
DEFINE FIELD url ON bai_dang TYPE option<string>;
DEFINE FIELD ngay_dang ON bai_dang TYPE datetime;
DEFINE FIELD tuong_tac ON bai_dang TYPE object;

DEFINE TABLE luan_diem SCHEMAFULL;
DEFINE FIELD bai_dang ON luan_diem TYPE record<bai_dang>;
DEFINE FIELD noi_dung ON luan_diem TYPE string;
DEFINE FIELD cam_xuc ON luan_diem TYPE string;

-- LINKING EDGES
DEFINE TABLE thao_luan_ve SCHEMAFULL;
DEFINE FIELD in ON thao_luan_ve TYPE record<khoan>;
DEFINE FIELD out ON thao_luan_ve TYPE record<luan_diem>;
DEFINE FIELD do_lien_quan ON thao_luan_ve TYPE float;

-- MISINFO (⚠️ KHÔNG phán đúng/sai tuyệt đối)
DEFINE TABLE kiem_chung SCHEMAFULL;
DEFINE FIELD luan_diem ON kiem_chung TYPE record<luan_diem>;
DEFINE FIELD muc_do ON kiem_chung TYPE string;  -- "phu_hop"|"can_doi_chieu"|"mau_thuan"
DEFINE FIELD giai_thich ON kiem_chung TYPE string;
DEFINE FIELD trich_dan ON kiem_chung TYPE array;
DEFINE FIELD do_tin_cay ON kiem_chung TYPE float;
```

---

## 4. Pipeline Architecture

**INSERT (async worker):** Upload VB → Regex Parser (M1) → LLM NER (M2) → Version Diff (M4) → Embed + Store
**QUERY (realtime):** Import MXH → Topic + Claim Extract (M3/M5) → Hybrid Retrieval (Vector + Graph) → LLM Re-rank → Link Edge
**FACTCHECK:** Claim → Query Routing → Citation-First Context → NLI Cross-Reference → Validate Citations → Output

---

## 5. Nguyên tắc bất di bất dịch

1. **KHÔNG** phán đúng/sai tuyệt đối → chỉ `phù hợp / cần đối chiếu / mâu thuẫn`
2. **KHÔNG** hardcode dữ liệu luật
3. **BẮT BUỘC** validate citation khớp text trong DB
4. **BẮT BUỘC** disclaimer "Công cụ hỗ trợ, không thay thế tư vấn pháp lý"

---

## 6. Timeline & Phân công

```
Hour  0 ════ 12 ════ 24 ════ 36 ════ 48
AI:   [Parser+NER]──[Diff+Social]──[MockData+E2E]──[Support]
BE:   [Docker+DB+Models]──[Legal API]──[Social+Misinfo]──[Deploy+Fix]
FE:   [Theme+Layout]──[Dashboard+Legal]──[Graph+Social+QA]──[Polish]
```

## 7. Demo Script (3 phút)

1. Upload luật → Parser tách Điều-Khoản-Điểm + entity tags
2. Dashboard → Thống kê + trend
3. Knowledge Graph → Connections trực quan
4. Social Feed → Cờ 🟢🟡🔴, click → giải thích + trích dẫn
5. Q&A Chat → Trả lời + citation chính xác
6. Kết luận → Kiến trúc, disclaimer

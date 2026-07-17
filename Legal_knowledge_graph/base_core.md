# Đồ Thị Tri Thức Pháp Luật + Giám Sát MXH — Tóm Tắt Đề Bài & Kế Hoạch Xây Dựng

## 1. Bối cảnh & mục tiêu

Từ 01/07/2026, nhiều luật/nghị định/thông tư mới có hiệu lực → nhu cầu nắm bắt tác động pháp lý nhanh, đồng thời MXH bùng nổ thảo luận và hiểu lầm về quy định mới.

**Mục tiêu:** Xây knowledge graph hợp nhất 2 miền dữ liệu — văn bản pháp luật (chính thống, có cấu trúc) và dư luận MXH (phi chính thống) — phục vụ:

1. **Phân hệ Admin** — cơ quan nhà nước số hóa luật, đối chiếu phiên bản, giám sát dư luận, cảnh báo rủi ro và gợi ý định hướng truyền thông.
2. **Phân hệ Citizen** — người dân nhận tóm tắt luật dễ hiểu và hỏi đáp có trích dẫn Điều–Khoản–Điểm.

**Nguyên tắc chung:** citation-first; misinfo chỉ gắn mức `khớp / mâu thuẫn / không rõ` (không phán đúng/sai tuyệt đối); Citizen chỉ tiêu thụ dữ liệu đã được Admin “tiêu hóa” và duyệt phát hành.

---

## 2. Hai phân hệ sản phẩm

```
                    ┌─────────────────────────────────────┐
                    │     Backend lõi (1 hệ thống)         │
                    │  KG · Vector · Pipelines · RAG API   │
                    └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                                         ▼
┌─────────────────────────────┐           ┌─────────────────────────────┐
│ Phân hệ 1: Admin Dashboard  │           │ Phân hệ 2: Citizen Portal   │
│ Cơ quan Nhà nước            │           │ Người dân                   │
│ • Legal Parser & NER        │  publish  │ • Bite-sized Legal News     │
│ • Versioning / Diff         │ ───────►  │ • Q&A Chatbot + Citations   │
│ • Knowledge Graph Explorer  │           │ • Tra cứu VB công khai      │
│ • Social Listening & Alerts │           │                             │
│ • Đề xuất đính chính        │           │ (read-only trên dữ liệu     │
│ • Jobs / Review / Publish   │           │  đã published)              │
└─────────────────────────────┘           └─────────────────────────────┘
```

| Phân hệ | Ai dùng | Việc cốt lõi | Không làm |
|---|---|---|---|
| **1. Admin Dashboard** | Cán bộ pháp chế, giám sát TT, quản trị dữ liệu | Ingest/parse luật, diff, KG, MXH, alerts, gợi ý đính chính, duyệt nội dung phát hành | Không công khai dữ liệu thô MXH / bản nháp chưa duyệt |
| **2. Citizen Portal** | Người dân | Đọc tin tóm tắt dễ hiểu, hỏi đáp có citation | Không ingest, không xem alerts nội bộ, không sửa KG |

---

## 3. Kiến trúc tổng quan (kỹ thuật)

```
[Nguồn luật] → Crawler → Parser Điều–Khoản–Điểm → Legal NER/RE ──┐
                                                                   ├→ Knowledge Graph (Neo4j)
[MXH/forum]  → Crawler → Topic classify → Entity linking ─────────┘   │
                                                                        ├→ Vector store
                                                          RAG QA Engine ┤
                                                    Misinfo detector    ┤
                                                    ContentBrief (tin)  ┤
                                                    ResponseSuggest     ┘
                                                                          │
                                                    ┌─────────────────────┴─────────────────────┐
                                                    ▼                                           ▼
                                          Admin API (RBAC đầy đủ)                    Citizen API (read/publish)
                                          Admin Dashboard                            Citizen Portal
```

---

## 4. Phân rã yêu cầu (9 module)

| # | Yêu cầu | Phân hệ chính | Bài toán kỹ thuật | Độ khó |
|---|---|---|---|---|
| 1 | Cấu trúc hóa Điều–Khoản–Điểm | Admin | Parsing văn bản pháp lý phân cấp, chuẩn hóa số hiệu | Trung bình |
| 2 | Trích xuất chủ thể/nghĩa vụ/quyền/cấm/thời hạn/chế tài | Admin | Legal NER + Relation Extraction | Cao |
| 3 | Theo dõi thảo luận MXH theo chủ đề | Admin | Thu thập + topic classification | Trung bình |
| 4 | Trích xuất thay đổi so với văn bản cũ | Admin | Version diffing theo nội dung | Cao |
| 5 | Liên kết bài đăng ↔ quy định | Admin | Semantic matching đời thường ↔ pháp lý | Rất cao |
| 6 | Phát hiện xu hướng/hiểu lầm (mức đối chiếu) | Admin | Stance + NLI; nhãn khớp/mâu thuẫn/không rõ | Rất cao |
| 7 | Q&A có trích dẫn (Admin nội bộ + Citizen) | Cả hai | RAG + chống hallucination citation | Cao |
| 8 | Trực quan hóa Knowledge Graph | Admin | Graph explorer / neighborhood view | Trung bình |
| 9 | Tin tóm tắt đại chúng + gợi ý đính chính | Admin→Citizen | Content generation có citation + human publish | Cao |

---

## 5. Ontology gợi ý

**Node:** VanBanPhapLuat, Dieu, Khoan, Diem, ChuThe, NghiaVu, QuyenLoi, HanhViCam, ThoiHan, CheTai, BaiDang, ChuDe, YKien, **BaiTomTat** (tin bite-sized), **DeXuatDinhChinh** (gợi ý phản hồi TT)

**Relation:** thuộc, quy_dinh, ap_dung_cho, thay_the/sua_doi, thao_luan_ve, gan_co_can_kiem_chung, **tom_tat_tu**, **de_xuat_cho_alert**, **published_as**

---

## 6. Gợi ý xây dựng từng module

| Module | Approach chính | Stack đề xuất |
|---|---|---|
| 1. Cấu trúc hóa văn bản | Regex state machine Điều/Khoản/Điểm; fallback LLM local | `pdfplumber`/`PyMuPDF`, `lxml`, gateway.py (Gemma local) |
| 2. Trích xuất thực thể pháp lý | LLM few-shot, ép JSON schema mỗi Khoản | Routing local/lớn qua 9R-Shield |
| 3. Giám sát MXH theo chủ đề | Zero-shot topic classification embedding VN | Facebook Graph API, YouTube API, `bge-m3`/`vietnamese-sbert` |
| 4. Trích xuất thay đổi | Regex dẫn chiếu tường minh + embedding similarity; LLM diff có cấu trúc | Cache cặp Khoản đã so sánh |
| 5. Liên kết bài đăng ↔ quy định | Retrieval 2 tầng: vector → LLM re-rank; MVP qua ChuDe | Vector DB (Qdrant/pgvector) |
| 6. Phát hiện hiểu lầm | Claim → NLI với Khoản đã link; chỉ mức khớp/mâu thuẫn/không rõ | — |
| 7. Q&A API | RAG (vector + graph), ép citation, validate substring nguyên văn | GPTCache+Redis; FastAPI |
| 8. Graph Explorer | Cypher neighborhood theo VB/Khoản/ChuThe; không sinh cạnh ảo | Neo4j + vis frontend |
| 9a. Bite-sized Legal News | Sinh tóm tắt ngôn ngữ bình dân từ Khoản/Điểm đã extract; **bắt buộc citation**; Admin duyệt mới `published` | LLM schema-locked + CMS trạng thái |
| 9b. Đề xuất đính chính | Từ cluster hiểu lầm phổ biến + Khoản đối chiếu → draft hướng dẫn/đính chính; Admin chỉnh & xuất bản | Chỉ gợi ý, không tự đăng MXH |

---

## 7. Thách thức trọng tâm

- Ánh xạ ngôn ngữ đời thường ↔ ngôn ngữ pháp lý (nút thắt lớn nhất, module #5)
- Xác định “cùng một vấn đề” giữa văn bản cũ/mới theo ngữ nghĩa, không chỉ số hiệu
- Gắn nhãn hiểu lầm mang rủi ro pháp lý-đạo đức nếu khẳng định sai → giữ wording mức đối chiếu
- Chống hallucination trích dẫn trong Q&A và trong tin tóm tắt là bắt buộc
- Tách quyền Admin/Citizen: không lộ dữ liệu MXH thô, alert nội bộ, bản nháp chưa duyệt
- ToS nền tảng và quyền riêng tư khi thu thập MXH
- Human-in-the-loop trước khi publish tin Citizen và trước khi dùng đề xuất đính chính ra ngoài

---

## 8. Phạm vi triển khai đề xuất

| Giai đoạn | Bao phủ | Phân hệ | Lý do |
|---|---|---|---|
| **Lõi (MVP)** | Module 1, 2, 4, 7 (+ QA Admin) | Admin + skeleton Citizen QA | Giá trị cốt lõi, khả thi ngắn hạn |
| **Mở rộng A** | Module 3, 5, 6, 8 | Admin đầy đủ | Giám sát + graph sau khi có lõi luật |
| **Mở rộng B** | Module 9a, 9b + Citizen Portal hoàn chỉnh | Citizen + publish flow | Cần dữ liệu đã “tiêu hóa” + quy trình duyệt |

**Tiêu chí đánh giá:** độ bao phủ văn bản đã cấu trúc hóa; độ chính xác trích xuất; độ chính xác liên kết bài–quy định; precision/recall mức đối chiếu; tỷ lệ citation đúng trong Q&A; % tin tóm tắt có citation hợp lệ trước publish; thời gian triage Alert → đề xuất đính chính.

---

## 9. Tài liệu hệ thống chi tiết & phân công

| File | Nội dung |
|---|---|
| `TEAM_ASSIGNMENT.md` | Phân công **3 Backend + 1 Frontend + 1 Database** + danh sách hệ thống bắt buộc |
| `Backend/SYSTEM_BACKEND.md` | Kiến trúc backend, ontology, API contract |
| `Backend/ROLE_BE1_LEGAL_PIPELINE.md` | BE1 — Parse / NER / Diff |
| `Backend/ROLE_BE2_SOCIAL_INTEL.md` | BE2 — MXH / LLM router / Brief–Suggest |
| `Backend/ROLE_BE3_API_QA_SERVICES.md` | BE3 — FastAPI / RAG QA / Auth / PublishGate |
| `Frontend/SYSTEM_FRONTEND.md` | Kiến trúc Admin + Citizen + map API §8.1 |
| `Frontend/ROLE_FRONTEND.md` | Việc FE chi tiết + stack UI |
| `Data/SYSTEM_DATA.md` | Neo4j / Postgres / Qdrant / Redis / MinIO + seed/gold |

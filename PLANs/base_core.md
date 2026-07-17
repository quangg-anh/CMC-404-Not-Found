# Đồ Thị Tri Thức Pháp Luật + Giám Sát MXH — Tóm Tắt Đề Bài & Kế Hoạch Xây Dựng

## 1. Bối cảnh & mục tiêu

Từ 01/07/2026, nhiều luật/nghị định/thông tư mới có hiệu lực → nhu cầu nắm bắt tác động pháp lý nhanh, đồng thời MXH bùng nổ thảo luận và hiểu lầm về quy định mới.

**Mục tiêu:** Xây knowledge graph hợp nhất 2 miền dữ liệu — văn bản pháp luật (chính thống, có cấu trúc) và dư luận MXH (phi chính thống) — phục vụ Q&A có trích dẫn và cảnh báo rủi ro truyền thông.

## 2. Kiến trúc tổng quan

```
[Nguồn luật] → Crawler văn bản → Parser phân cấp → Legal NER/RE ──┐
                                                                    ├→ Knowledge Graph (Neo4j...)
[MXH/forum]  → Crawler social  → Topic classifier → Entity linking┘   │
                                                                        ├→ Vector store (embedding Khoản/Điểm + bài đăng)
                                                          RAG QA Engine ┘→ Dashboard + API (kèm trích dẫn)
                                                    Misinformation detector
```

## 3. Phân rã 7 yêu cầu

| # | Yêu cầu | Bài toán kỹ thuật | Độ khó |
|---|---|---|---|
| 1 | Cấu trúc hóa Điều–Khoản–Điểm | Parsing văn bản pháp lý phân cấp, chuẩn hóa số hiệu | Trung bình |
| 2 | Trích xuất chủ thể/nghĩa vụ/quyền lợi/hành vi cấm/thời hạn/chế tài | Legal NER + Relation Extraction | Cao |
| 3 | Theo dõi thảo luận MXH theo chủ đề | Thu thập dữ liệu + topic classification | Trung bình |
| 4 | Trích xuất thay đổi so với văn bản cũ | Version diffing theo nội dung (không chỉ số hiệu) | Cao |
| 5 | Liên kết bài đăng ↔ quy định | Semantic matching ngôn ngữ đời thường ↔ ngôn ngữ pháp lý | Rất cao |
| 6 | Phát hiện xu hướng/hiểu lầm/tin sai lệch | Stance detection + fact-checking tự động | Rất cao |
| 7 | Dashboard/API Q&A có trích dẫn | RAG + kiểm soát hallucination | Cao |

## 4. Ontology gợi ý

**Node:** VanBanPhapLuat, Dieu, Khoan, Diem, ChuThe, NghiaVu, QuyenLoi, HanhViCam, ThoiHan, CheTai, BaiDang, ChuDe, YKien

**Relation:** thuộc, quy_dinh, ap_dung_cho, thay_the/sua_doi, thao_luan_ve, gan_co_can_kiem_chung

## 5. Gợi ý xây dựng từng module

| Module | Approach chính | Stack đề xuất |
|---|---|---|
| 1. Cấu trúc hóa văn bản | Regex state machine theo mốc Điều/Khoản/Điểm; fallback LLM local cho format lệch chuẩn | `pdfplumber`/`PyMuPDF`, `lxml`, gateway.py (Gemma local) |
| 2. Trích xuất thực thể pháp lý | LLM few-shot extraction, ép JSON schema cố định mỗi Khoản | Routing local/lớn qua 9R-Shield theo độ phức tạp Khoản |
| 3. Giám sát MXH theo chủ đề | Zero-shot topic classification bằng embedding tiếng Việt | Facebook Graph API, YouTube API, `bge-m3`/`vietnamese-sbert` |
| 4. Trích xuất thay đổi | Regex bắt cụm dẫn chiếu tường minh + embedding similarity cho phần còn lại; LLM sinh diff có cấu trúc | Cache cặp Khoản đã so sánh |
| 5. Liên kết bài đăng ↔ quy định | Retrieval 2 tầng: vector search → LLM re-rank xác nhận; MVP nên qua lớp trung gian ChuDe trước | Vector DB (Qdrant/pgvector) |
| 6. Phát hiện hiểu lầm/tin sai lệch | Trích claim từ bài đăng → so khớp Khoản đã link bằng NLI; chỉ gắn "mức độ khớp/mâu thuẫn", không phán đúng/sai tuyệt đối | — |
| 7. Dashboard + Q&A API | RAG (vector + graph traversal), ép output kèm citation, validate câu trích khớp nguyên văn | Cache semantic (GPTCache+Redis) cho câu hỏi trùng lặp qua 9R-Shield; Streamlit/FastAPI cho MVP |

## 6. Thách thức trọng tâm

- Ánh xạ ngôn ngữ đời thường ↔ ngôn ngữ pháp lý (nút thắt lớn nhất, module #5)
- Xác định "cùng một vấn đề" giữa văn bản cũ/mới cần đối chiếu ngữ nghĩa, không chỉ số hiệu
- Gắn nhãn "sai lệch" mang rủi ro pháp lý-đạo đức nếu khẳng định sai
- Chống hallucination trích dẫn trong Q&A là bắt buộc, không phải tùy chọn
- Cần cân nhắc ToS nền tảng và quyền riêng tư khi thu thập dữ liệu MXH

## 7. Phạm vi triển khai đề xuất

| Giai đoạn | Bao phủ | Lý do |
|---|---|---|
| Lõi (MVP) | Module 1, 2, 4, 7 | Khả thi trong thời gian ngắn, giá trị cốt lõi |
| Mở rộng | Module 3, 5, 6 | Phụ thuộc lõi làm nền, độ khó NLP cao hơn — demo ở quy mô nhỏ (1-2 chủ đề luật) |

**Tiêu chí đánh giá:** độ bao phủ văn bản đã cấu trúc hóa, độ chính xác trích xuất thực thể, độ chính xác liên kết bài đăng–quy định, precision/recall phát hiện sai lệch, tỷ lệ trích dẫn đúng trong Q&A.
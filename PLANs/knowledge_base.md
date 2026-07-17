# LexSocial AI — Technology & Idea Knowledge Base

Tài liệu này lưu trữ toàn bộ các ý tưởng công nghệ, nguyên lý thiết kế và phân tích chiến lược được thu thập trong quá trình nghiên cứu, chuẩn bị cho việc xây dựng bản kế hoạch chi tiết của LexSocial AI.

---

## 1. Triết lý hệ thống RAG quy mô lớn (Near-Zero Hallucination)
*Nguồn tham khảo: Bài viết "Building a RAG Pipeline for 10M+ Documents"*

Để giảm thiểu tình trạng AI "bịa" câu trả lời (hallucination) trong lĩnh vực pháp luật, hệ thống tuân theo vòng lặp 4 bước:
1. **Retrieve (Truy xuất):** Tìm kiếm dữ liệu từ Database (Vector + Keyword + Graph).
2. **Constrain (Ràng buộc):** Ép LLM chỉ được phép trả lời dựa TẬP TRUNG vào những context vừa truy xuất, vô hiệu hóa các kiến thức pre-trained có thể sai lệch.
3. **Verify (Xác minh):** Đối chiếu chéo (Cross-reference) xem từng câu chữ trong câu trả lời có khớp với bản gốc không.
4. **Abstain (Từ chối):** Nếu không chắc chắn, hệ thống phải báo "Cần đối chiếu" thay vì đoán bừa.

### Các kỹ thuật tối ưu Data Ingestion & Retrieval:
- **MinHash LSH:** Loại bỏ các văn bản/đoạn trùng lặp (near-duplicates).
- **Structure-aware chunks:** Cắt văn bản không cắt mù quáng theo số lượng từ, mà cắt theo cấu trúc `Điều-Khoản-Điểm`.
- **One-line context prefix:** Mỗi chunk phải được gắn thêm tiền tố (VD: *"Thuộc Điều 5, Luật Đất đai 2024..."*) để bảo toàn ngữ cảnh cho Vector Search.
- **Hybrid Indexing & RRF:** Kết hợp Dense Vector (tìm kiếm ngữ nghĩa) và Sparse/BM25 (tìm kiếm từ khóa). Kết quả được trộn lại bằng thuật toán Reciprocal Rank Fusion (RRF).
- **LLM Rerank:** Lấy top 150 kết quả từ RRF, dùng model nhỏ chấm điểm lại để chọn ra top 20 chính xác nhất.
- **Route & Decompose:** Phân loại và bẻ gãy câu hỏi phức tạp thành nhiều câu hỏi nhỏ trước khi tìm kiếm.

---

## 2. Kiến trúc Đồ thị Tri thức (LightRAG-inspired)
*Nguồn tham khảo: Báo cáo LightRAG vs LLM Notebook hiện tại*

LightRAG mạnh hơn RAG truyền thống vì nó vừa lưu Text Vector, vừa lưu Entity/Relationship. Tuy nhiên bản nguyên gốc rất nặng nề (monolithic).
**Áp dụng vào LexSocial AI:** Tách thành 2 pipeline bất đồng bộ chạy trên SurrealDB (vừa hỗ trợ Vector, vừa hỗ trợ Graph Relational).

### Insert Pipeline (Chạy ngầm - Ingestion)
- Chặt nhỏ văn bản theo Điều-Khoản-Điểm.
- Dùng LLM (few-shot) trích xuất **Thực thể (Entities)**: Chủ thể, Nghĩa vụ, Quyền, Thời hạn, Mức phạt.
- Dùng LLM trích xuất **Quan hệ (Relationships)**: Điều A -> quy định -> Nghĩa vụ B -> phạt -> Mức C.
- Gộp các Node/Edge trùng lặp.
- Lưu tất cả Embeddings (Chunk + Entity) và Edges vào SurrealDB.

### Query Pipeline (Realtime - Retrieval)
- **Keyword/Claim Extraction:** Tóm tắt ý chính từ bài đăng MXH.
- **Hybrid Graph+Vector Search:** Tìm Vector gần nhất, sau đó nhảy (Graph Traversal) sang các Node liên quan trong SurrealDB để lấy thêm ngữ cảnh (Multi-hop reasoning).
- **Citation-First Prompting:** Prompt LLM bắt buộc liệt kê "Điều/Khoản" làm căn cứ TRƯỚC KHI viết câu trả lời.

---

## 3. Phân tách 7 Module theo Đề bài Hackathon

1. **Parser Văn bản:** Cấu trúc hóa Điều-Khoản-Điểm. Dùng Regex State Machine trước, LLM Fallback sau.
2. **NER (Named Entity Recognition):** Bóc tách chủ thể/hành vi bằng LLM few-shot với JSON schema chặt chẽ.
3. **Theo dõi MXH:** Phân loại Topic zero-shot bằng tiếng Việt (bge-m3 / vietnamese-sbert).
4. **Phân tích thay đổi Luật:** Bắt Regex các cụm "sửa đổi, thay thế". Dùng Cosine Similarity tìm Điều luật tương đồng giữa luật cũ/mới để LLM sinh bản diff JSON.
5. **Entity Linking MXH ↔ Luật:** Dùng Retrieval 2 tầng (Vector Top-K -> LLM Rerank) để giải quyết khoảng cách ngữ nghĩa giữa teencode và ngôn ngữ luật.
6. **Misinfo Detection (Phát hiện sai lệch):** Áp dụng NLI (Natural Language Inference). Đối chiếu claim từ MXH vs luật.
7. **Dashboard/API Q&A:** Áp dụng Caching Semantic (Cache các câu hỏi giống nhau để trả lời ngay, tiết kiệm phí LLM). 

---

## 4. Quản trị Rủi ro (Critical Boundaries)

- **Tuyệt đối không phán "Đúng / Sai" tuyệt đối:** Ngăn ngừa rủi ro pháp lý/đạo đức. Hệ thống chỉ gắn nhãn: `Phù hợp` / `Cần đối chiếu` / `Mâu thuẫn`. Đi kèm BẮT BUỘC là trích dẫn Điều luật gốc để người đọc tự quyết.
- **Không hardcode:** Toàn bộ data phải được ingest qua API.
- **Anti-Hallucination:** Output của LLM phải được hậu kiểm (post-validation) để đảm bảo các trích dẫn (citations) sinh ra thực sự tồn tại (khớp text) trong Database.

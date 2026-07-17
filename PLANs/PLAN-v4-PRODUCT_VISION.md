# LexSocial AI — PLAN v4 (PRODUCT VISION)

> **Tagline:** Đồ thị tri thức pháp luật — Giải mã quy định, Minh bạch thông tin đại chúng
> **Repo:** https://github.com/antondung/CMC-404-Not-Found
> **Base:** open-notebook v1.13.0 (FastAPI + LangGraph + SurrealDB + Next.js)
> **Mục tiêu Hackathon (48h):** Xây dựng MVP với 2 phân hệ người dùng riêng biệt.

Bản thiết kế này biến các module kỹ thuật phức tạp (RAG, Knowledge Graph, NLI) thành một sản phẩm có tính ứng dụng thực tiễn cao, chia làm 2 phân hệ: **Cơ quan nhà nước (Admin)** và **Người dân (Citizen)**.

---

## PHẦN 1: TỔNG QUAN HAI PHÂN HỆ SẢN PHẨM

### 1. Phân hệ 1: Admin Dashboard (Dành cho Cơ quan Nhà nước)
Đây là "Trung tâm chỉ huy" (Command Center) dùng AI để bóc tách luật và theo dõi dư luận.

| Tính năng | Mô tả UI/UX | Công nghệ ngầm (Backend) |
|-----------|-------------|-------------------------|
| **Lõi phân tích & Số hóa Luật** | Giao diện Upload văn bản mới. Hiển thị kết quả bóc tách thành cây Điều–Khoản–Điểm rõ ràng. | `LegalParserGraph` (Regex + LLM NER để trích xuất Chủ thể, Nghĩa vụ, Chế tài...). |
| **So sánh đối chiếu (Versioning)** | Giao diện split-screen (chia đôi màn hình), highlight màu xanh/đỏ những đoạn luật mới thay đổi so với luật cũ (VD: phạt tăng từ 2tr lên 5tr). | Thuật toán `Version Diffing` (Cosine similarity + LLM diff generation). |
| **Bản đồ Tri thức (Knowledge Graph)** | Màn hình Canvas tương tác (Force-directed graph) hiển thị mạng lưới liên kết giữa các bộ luật và thực thể pháp lý. | `SurrealDB` Graph Query (`RELATE`, `->`). Frontend dùng `react-force-graph`. |
| **Radar Giám sát Dư luận** | Feed bài viết MXH được tự động gán cờ: 🔴 Mâu thuẫn (Hiểu sai), 🟡 Cần đối chiếu, 🟢 Phù hợp. Kèm theo cảnh báo rủi ro bùng nổ truyền thông. | `SocialLinkerGraph` (Zero-shot topic classification) + `MisinfoDetectorGraph` (NLI cross-reference). |
| **Gợi ý Đính chính** | Khi có 1 luồng tin sai lệch nổi lên, có nút "Gợi ý đính chính", AI sẽ tự động soạn sẵn 1 bài đăng chuẩn chỉnh để cán bộ copy đăng lên MXH. | LLM sinh text dựa trên `Citation-First Context` của các văn bản luật bị hiểu sai. |

### 2. Phân hệ 2: Citizen Portal (Dành cho Người dân)
Giao diện portal tối giản, thân thiện, biến ngôn ngữ pháp lý hàn lâm thành thông tin dễ hiểu.

| Tính năng | Mô tả UI/UX | Công nghệ ngầm (Backend) |
|-----------|-------------|-------------------------|
| **Tin tức Pháp luật (Bite-sized)** | Feed tin tức dạng thẻ (cards) giống mạng xã hội. AI tự động tóm tắt các luật mới thành ngôn ngữ bình dân, ngắn gọn. | `BiteSizedNewsGenerator` (Lấy dữ liệu từ Graph, dùng prompt ép giọng văn dễ hiểu, không jargon). |
| **Trợ lý ảo Pháp lý (Q&A Chatbot)** | Khung chat trực quan. Người dân gõ câu hỏi đời thường (VD: "Quên xi nhan phạt bao nhiêu?"). AI trả lời nhanh chóng. | Hybrid RAG (Vector + Keyword) qua thuật toán `RRF`. |
| **Minh bạch & Trích dẫn** | Dưới mỗi câu trả lời của Chatbot luôn có thẻ "Căn cứ pháp lý". Click vào sẽ trỏ thẳng đến nguyên văn Điều/Khoản luật trong Database. | `Citation-First Prompting` (Bắt LLM liệt kê nguồn trước khi trả lời). |

---

## PHẦN 2: KIẾN TRÚC KỸ THUẬT (MAPPING TỪ PRODUCT VISION)

Dựa trên kho tàng kiến thức từ bài RAG 10 Triệu Document và kiến trúc LightRAG, đây là cách ta xây dựng phần ngầm cho 2 Phân hệ trên.

### 2.1 Cơ sở dữ liệu (SurrealDB Schema rút gọn)
Sử dụng mô hình Graph-Relational lai.
- **Nodes:** `van_ban`, `dieu`, `khoan`, `diem`, `thuc_the` (NER), `bai_dang` (Social), `tin_tuc` (Bite-sized).
- **Edges:** `sua_doi` (Version diff), `thao_luan_ve` (Link MXH), `can_kiem_chung` (Misinfo flag).

### 2.2 Các Luồng Pipeline cốt lõi (LangGraph Workflows)

**Luồng 1: Legal Ingestion (Dành cho Admin - Lõi phân tích)**
Upload Text → Cắt mảnh theo cấu trúc (Điều-Khoản) kèm One-line prefix → Trích xuất Entity → Tìm khác biệt với luật cũ (Version Diff) → Lưu Vector + Edge.

**Luồng 2: Social Radar (Dành cho Admin - Radar Giám sát)**
Cào MXH (Mock data) → Rút trích luận điểm (Claim) → Tìm vector Khoản luật tương ứng (Hybrid RRF) → Đối chiếu bằng NLI (Khớp / Mâu thuẫn) → Cảnh báo.

**Luồng 3: Citizen Q&A (Dành cho Citizen - Trợ lý ảo)**
Nhận câu hỏi → Route & Decompose (Phân rã câu hỏi) → Truy xuất Hybrid (Vector + Graph) → Buộc LLM trích dẫn nguồn (Constrain) → Trả lời (Verify & Abstain nếu không chắc).

---

## PHẦN 3: KẾ HOẠCH TRIỂN KHAI 48H (MVP)

Mục tiêu là code ra được một Demo sắc nét, show rõ được UI của Admin và Citizen.

### Phase 1: Móng kỹ thuật & Database (Hour 0 - 12)
- Khởi tạo SurrealDB schema bằng tiếng Việt.
- Viết API Router cho Legal (Upload & Parse).
- Xây dựng `LegalParserGraph` (Dùng Regex bóc tách cấu trúc Điều/Khoản trước, sau đó dùng LLM trích NER).

### Phase 2: Phát triển Backend Logic (Hour 12 - 28)
- Xây dựng luồng Q&A Chatbot với Citation-First (`MisinfoDetectorGraph`).
- Xây dựng luồng Versioning (So sánh luật cũ mới).
- Viết prompt cho Bite-sized News Generator.
- Mock 50 bài đăng MXH để làm data cho Radar Giám sát.

### Phase 3: Xây dựng UI/UX 2 Phân hệ (Hour 0 - 36, song song)
**Admin Dashboard (`/admin`):**
- Layout tối màu (Dark/Navy blue), mang tính nghiệp vụ cao.
- Component: Upload Form, Split-screen Diffing, Bảng danh sách Cảnh báo MXH đỏ/vàng/xanh, Nút "Tạo bài đính chính".
- Tích hợp `react-force-graph` hiển thị Đồ thị tri thức.

**Citizen Portal (`/`):**
- Layout sáng sủa, typography to, thân thiện (Clean/Minimalist).
- Component: Feed tin tức Bite-sized, Nút Chat nổi. UI Chat hiển thị trích dẫn đẹp mắt.

### Phase 4: Ghép nối & Chuẩn bị Demo (Hour 36 - 48)
- Kết nối Frontend gọi API Backend.
- Test kịch bản Demo từ đầu đến cuối. Deploy (Railway/Render).

---

## KỊCH BẢN DEMO GIÁM KHẢO (3 PHÚT)

1. **(15s)** Mở màn: Tuyên bố giải quyết bài toán khủng hoảng truyền thông chính sách từ ngày 01/07/2026.
2. **(45s) Show Admin Dashboard:** Upload 1 nghị định giao thông mới. Show hệ thống tự động băm nhỏ ra Điều/Khoản, vẽ lên Đồ thị tri thức, và ĐẶC BIỆT show tính năng Versioning (đỏ/xanh) so với luật cũ.
3. **(60s) Show Radar Dư luận:** Chuyển qua tab Radar, show hàng loạt bài post MXH đang than phiền sai luật. Click vào 1 bài bị gắn cờ 🔴 Mâu thuẫn, show hệ thống tự động chỉ ra người dân sai ở Khoản mấy, và bấm nút "Auto-Đính chính" để ra bài giải thích.
4. **(45s) Show Citizen Portal:** Mở portal cho người dân, show các thẻ tin tức tóm tắt siêu dễ hiểu. Mở Chatbot, hỏi 1 câu teencode. Bot trả lời siêu chuẩn kèm Trích dẫn bấm vào được (Citation).
5. **(15s)** Kết luận: Nhấn mạnh công nghệ "Near-Zero Hallucination" và khả năng triển khai thực tế ngay ngày mai.

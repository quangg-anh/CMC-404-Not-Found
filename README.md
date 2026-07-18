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

Hệ thống LexSocial AI bao gồm hai giao diện web chính được tối ưu hóa cho trải nghiệm người dùng:

### 1️⃣ Phân hệ Admin Dashboard
*Dành cho cơ quan nhà nước, cán bộ pháp chế, giám sát truyền thông, quản trị dữ liệu.*

- Cung cấp bộ công cụ mạnh mẽ để cán bộ pháp chế quản lý kho dữ liệu luật, theo dõi biểu đồ thống kê từ mạng xã hội (tích hợp Nivo và Vis-network để trực quan hóa Đồ thị Tri thức).
- **Số hóa văn bản pháp luật**: Tải lên PDF/HTML, tự động bóc tách cấu trúc (Điều, Khoản, Điểm) bằng NLP, lưu vào Neo4j và Qdrant.
- **Theo dõi phiên bản (Version Diff)**: Tìm điểm khác biệt giữa các phiên bản luật, tự động tạo diff và ghi chú.
- **Giám sát dư luận (Social Listening)**: Thu thập dữ liệu từ mạng xã hội, phân loại chủ đề (Topic Classification), và đối chiếu mức độ khớp với luật hiện hành (NLI).
- **Cảnh báo rủi ro**: Xử lý các cảnh báo rủi ro theo thời gian thực (gắn nhãn `khớp / mâu thuẫn / không rõ`).
- **Gợi ý & Xuất bản**: Duyệt đề xuất đính chính truyền thông, và xuất bản nội dung (Publish) ra công chúng.

### 2️⃣ Phân hệ Citizen Portal
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
- **Embedding:** `bge-m3` / `vietnamese-sbert` hỗ trợ tiếng Việt.
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
- **Kiến trúc Monorepo (Vite):** Quản lý 2 apps độc lập (`admin`, `citizen`) và shared packages (`ui-legal`, `api-client`).
- **State Management & UI:** React Query, TailwindCSS, Vis-network / Nivo (Vẽ đồ thị).

---

## 🚀 Hướng dẫn Cài đặt & Khởi chạy (Local Development)

Dự án cung cấp một script hợp nhất `run.ps1` (trên PowerShell/Windows) hoặc bạn có thể khởi chạy từng phần.

### Yêu cầu hệ thống
- **Python** 3.10+
- **Node.js** 20 LTS+
- **Docker & Docker Compose**
- **Ollama** (Đã cài sẵn model `bge-m3` để làm embedding: `ollama pull bge-m3`)

### Các bước khởi chạy

#### 1. Khởi động Data Stack (Các DB & Storage)
Mở terminal trong thư mục gốc dự án và chạy Docker:
```bash
docker-compose -f Data/docker-compose.data.yml --env-file Data/.env up -d
```
*(Khởi chạy: Postgres, Neo4j, Qdrant, Redis, MinIO).*

#### 2. Cài đặt Dependency và Khởi chạy Ứng dụng
Sử dụng script PowerShell `run.ps1` để tự động tạo môi trường ảo Python (venv), cài đặt thư viện (`pip`, `npm`), seed dữ liệu mẫu, và bật các services:

```powershell
# Chạy lần đầu tiên (có cài đặt dependency)
./run.ps1 -Install

# Những lần sau chỉ cần chạy
./run.ps1
```

Script này sẽ tự động bật các cửa sổ mới cho Backend (FastAPI), Worker (Arq), và Frontend (Vite).

#### 3. Truy cập Hệ thống
Sau khi khởi chạy thành công, bạn có thể truy cập qua các địa chỉ sau:

- **Frontend Admin:** [http://localhost:5173/admin/](http://localhost:5173/admin/)
  - Tài khoản kiểm thử: `admin@local` / `admin123`
- **Frontend Citizen:** [http://localhost:5174/citizen/](http://localhost:5174/citizen/)
  - Truy cập công khai, tự do trải nghiệm không cần đăng nhập.
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
- **Kiểm thử (Testing):** Dự án sử dụng `pytest`. Bạn có thể chạy unit test cho các pipeline xử lý luật bằng lệnh:
  ```powershell
  cd Backend
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

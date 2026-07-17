import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Giả định root dir của dự án dựa trên vị trí file hiện tại (Backend/app/pipelines/legal/ingest.py)
# Backend/app/pipelines/legal/ingest.py -> Backend -> CMC-404-Not-Found
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_RAW_DIR = PROJECT_ROOT / "Data" / "raw" / "legal"

class LegalIngester:
    """
    Module phụ trách tiếp nhận file (Ingest) cho Legal Pipeline (BE1).
    Nhiệm vụ: 
    1. Nhận file bytes.
    2. Tính checksum SHA-256 để chống trùng lặp (Idempotent).
    3. Lưu trữ file nguyên bản không thay đổi (immutable) vào MinIO hoặc Local.
       (Tại Phase A, fallback lưu local vào Data/raw/legal/{yyyy}/{checksum}/{filename}).
    4. Trả về payload chuẩn bị để tạo job 'legal_ingest'.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or DATA_RAW_DIR
        # Đảm bảo thư mục lưu trữ tồn tại
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def calculate_checksum(self, file_bytes: bytes) -> str:
        """Tính mã băm SHA-256 của file."""
        return hashlib.sha256(file_bytes).hexdigest()

    def process_file(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Xử lý file tải lên, lưu vào cấu trúc: Data/raw/legal/{yyyy}/{checksum}/{filename}
        Trả về payload thông tin metadata sẵn sàng cung cấp cho Postgres và Arq/Celery Worker.
        """
        if not file_bytes:
            raise ValueError("Không có nội dung file (empty bytes).")
            
        checksum = self.calculate_checksum(file_bytes)
        current_year = str(datetime.now(timezone.utc).year)

        # Xây dựng đường dẫn đích: /Data/raw/legal/yyyy/checksum/filename
        target_dir = self.storage_dir / current_year / checksum
        target_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = target_dir / filename
        
        # Đảm bảo tính Immutable (Bất biến): Không ghi đè nếu file trùng checksum đã tồn tại
        if not file_path.exists():
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            logger.info(f"Đã lưu thành công file thô gốc tại: {file_path}")
        else:
            logger.info(f"File gốc đã tồn tại với checksum {checksum}, bỏ qua việc ghi đè.")

        # Trả về payload. Payload này sẽ được API /admin/ingest/legal 
        # hứng lấy để đẩy vào queue chạy `legal_parse` (ở file workers/legal_jobs.py).
        payload = {
            "checksum": checksum,
            "filename": filename,
            "storage_key": f"legal/{current_year}/{checksum}/{filename}",
            "absolute_path": str(file_path.absolute()),
            "size_bytes": len(file_bytes),
            "ingested_at": datetime.now(timezone.utc).isoformat()
        }
        
        return payload

# Ví dụ luồng sử dụng (dành cho BE3 FastAPI gọi):
# ingester = LegalIngester()
# result_payload = ingester.process_file(pdf_bytes, "nghi_dinh_15_2020.pdf")
# => Sau đó enqueue result_payload vào Redis cho legal_parse worker xử lý

import logging
from typing import Dict, Any
from domain.legal_schemas import KhoanEntities

logger = logging.getLogger(__name__)

class LegalExtractor:
    """
    Trích xuất các thực thể pháp lý (NER/RE) từ nội dung của từng Khoản
    bằng cách gọi LLM theo định dạng JSON Schema cố định (schema-locked).
    """
    def __init__(self):
        # Lấy JSON Schema chuẩn từ Pydantic để nhúng vào prompt cho LLM
        self.schema = KhoanEntities.model_json_schema()

    def extract_entities_from_khoan(self, khoan_id: str, khoan_text: str) -> Dict[str, Any]:
        """
        Sử dụng LLM (giả lập thông qua giao diện router của BE2) để parse text 
        thành các thực thể pháp lý: ChuThe, NghiaVu, QuyenLoi, HanhViCam, v.v.
        """
        logger.info(f"Bắt đầu trích xuất thực thể cho Khoản [{khoan_id}]...")
        
        # TODO: Sử dụng httpx POST đến LLM router endpoint của BE2
        # `llm_complete(task="extract", prompt=khoan_text, schema=self.schema, complexity="large")`
        
        # Giả lập (Mock) kết quả từ LLM đã được map đúng schema
        mock_llm_result = {
            "chu_the": [{"mo_ta": "Cơ quan nhà nước", "nguon_khoan_id": khoan_id}],
            "nghia_vu": [{"mo_ta": "Phải công khai thông tin trên cổng điện tử", "nguon_khoan_id": khoan_id}],
            "quyen_loi": [],
            "hanh_vi_cam": [],
            "thoi_han": [{"mo_ta": "Chậm nhất là 15 ngày kể từ ngày ban hành", "nguon_khoan_id": khoan_id}],
            "che_tai": []
        }
        
        try:
            # Ép kiểu và validate bằng Pydantic để đảm bảo format JSON LLM nhả ra là chuẩn xác 100%
            validated_data = KhoanEntities(**mock_llm_result)
            return validated_data.model_dump()
        except Exception as e:
            logger.error(f"Lỗi validate schema JSON từ LLM cho Khoản {khoan_id}: {e}")
            # Trả về cờ lỗi để retry hoặc đẩy vào hàng đợi review
            return {"error": "extract_schema_fail"}

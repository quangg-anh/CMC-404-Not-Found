import re
import logging
from typing import List, Dict, Any, Tuple
# import pdfplumber  # Sẽ bật khi cấu hình môi trường có pdfplumber

logger = logging.getLogger(__name__)

# Regex Patterns chuẩn hóa để nhận diện cấu trúc Luật/Nghị định/Thông tư Việt Nam
# Ví dụ: "Điều 1. Phạm vi điều chỉnh", "Điều 15: Quy định chung"
REGEX_DIEU = re.compile(r'^Điều\s+(\d+)[.:]\s*(.*)', re.IGNORECASE)
# Ví dụ: "1. Uỷ ban nhân dân cấp tỉnh có trách nhiệm...", "2. ..."
REGEX_KHOAN = re.compile(r'^(\d+)\.\s+(.*)')
# Ví dụ: "a) Trách nhiệm của công dân...", "đ) ..."
REGEX_DIEM = re.compile(r'^([a-zđ])\)\s+(.*)')

class LegalParser:
    """
    Parser sử dụng cấu trúc Regex State Machine để biến đổi text thô thành cây:
    Văn Bản -> Điều -> Khoản -> Điểm.
    Đồng thời tích hợp cơ chế phát hiện nhiễu format để bật cờ needs_review.
    """
    
    def __init__(self):
        # Trạng thái hiện tại của State Machine khi quét qua từng dòng
        self.current_dieu = None
        self.current_khoan = None
        
    def extract_text_from_pdf(self, file_path: str) -> str:
        """
        Trích xuất toàn bộ text từ file PDF (Sử dụng pdfplumber).
        """
        try:
            import pdfplumber
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
        except ImportError:
            logger.error("Thư viện pdfplumber chưa được cài đặt.")
            return ""
        except Exception as e:
            logger.error(f"Lỗi khi đọc file PDF {file_path}: {e}")
            return ""

    def parse_text(self, text: str) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Quét qua text để build cây Điều-Khoản-Điểm.
        Trả về (Cây dữ liệu, cờ needs_review).
        """
        lines = text.split('\n')
        tree = []
        needs_review = False
        
        self.current_dieu = None
        self.current_khoan = None
        
        for line_raw in lines:
            line = line_raw.strip()
            if not line:
                continue
                
            # 1. Bắt dòng Điều
            match_dieu = REGEX_DIEU.match(line)
            if match_dieu:
                dieu_so = match_dieu.group(1)
                tieu_de_dieu = match_dieu.group(2)
                
                self.current_dieu = {
                    "loai": "Dieu",
                    "so": dieu_so,
                    "tieu_de": tieu_de_dieu,
                    "noi_dung": "",
                    "khoan_list": []
                }
                tree.append(self.current_dieu)
                self.current_khoan = None
                continue
                
            # 2. Bắt dòng Khoản (chỉ có hiệu lực nếu đang đứng trong 1 Điều)
            match_khoan = REGEX_KHOAN.match(line)
            if match_khoan and self.current_dieu is not None:
                khoan_so = match_khoan.group(1)
                noi_dung_khoan = match_khoan.group(2)
                
                self.current_khoan = {
                    "loai": "Khoan",
                    "so": khoan_so,
                    "noi_dung": noi_dung_khoan,
                    "diem_list": []
                }
                self.current_dieu["khoan_list"].append(self.current_khoan)
                continue
                
            # 3. Bắt dòng Điểm (chỉ có hiệu lực nếu đang đứng trong 1 Khoản)
            match_diem = REGEX_DIEM.match(line)
            if match_diem and self.current_khoan is not None:
                ky_hieu_diem = match_diem.group(1)
                noi_dung_diem = match_diem.group(2)
                
                diem_obj = {
                    "loai": "Diem",
                    "ky_hieu": ky_hieu_diem,
                    "noi_dung": noi_dung_diem
                }
                self.current_khoan["diem_list"].append(diem_obj)
                continue
                
            # 4. Xử lý Multi-line: Các đoạn văn kéo dài nhiều dòng 
            # (Gắn vào nấc sâu nhất hiện tại của State Machine)
            if self.current_khoan is not None:
                if self.current_khoan["diem_list"]:
                    self.current_khoan["diem_list"][-1]["noi_dung"] += " " + line
                else:
                    self.current_khoan["noi_dung"] += " " + line
            elif self.current_dieu is not None:
                self.current_dieu["noi_dung"] += " " + line
            else:
                # Bỏ qua các text trước khi Điều 1 bắt đầu (thường là Header/Căn cứ pháp lý)
                pass

        # Bật cờ needs_review nếu văn bản dài mà không bắt được Điều nào 
        # (Dấu hiệu của OCR rác, PDF lệch layout hoặc scan)
        if len(tree) == 0 and len(text.strip()) > 500:
            logger.warning("Không trích xuất được Điều nào. Khả năng layout lỗi, cần gọi LLM Fallback.")
            needs_review = True
            
        return tree, needs_review

    def fallback_llm_parse(self, text: str):
        """
        Nếu needs_review = True, hàm này sẽ gọi LLM Gateway (9R-Shield của BE2) 
        để ép LLM trả về cấu trúc JSON cây y hệt như hàm parse_text phía trên.
        """
        logger.info("Đang gọi LLM fallback từ BE2 để sửa cấu trúc lỗi...")
        # TODO: Implement httpx POST đến LLM router endpoint của BE2
        raise NotImplementedError("LLM Fallback call to BE2 router is not implemented yet.")

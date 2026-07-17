import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Regex tìm dẫn chiếu tường minh: Ví dụ "sửa đổi, bổ sung Điều 5"
REGEX_SUA_DOI = re.compile(
    r'(sửa đổi|bổ sung|thay thế|bãi bỏ).*?(điều|khoản|điểm)\s+([0-9a-zđ]+)', 
    re.IGNORECASE
)

class VersionDiff:
    """
    So sánh thay đổi (Diffing) giữa hai phiên bản văn bản hoặc hai Khoản luật.
    Mục tiêu sinh ra các Hunk (đoạn thay đổi) để Admin dễ đọc và sinh ContentBrief.
    """
    
    def extract_explicit_references(self, text: str) -> List[Dict[str, str]]:
        """
        Dùng Regex để tìm ra các dẫn chiếu tường minh về việc sửa đổi, bổ sung.
        Rất hữu ích cho các Nghị định chuyên về việc "Sửa đổi, bổ sung một số điều..."
        """
        matches = REGEX_SUA_DOI.finditer(text)
        results = []
        for match in matches:
            action = match.group(1).lower()
            target_type = match.group(2).lower()
            target_id = match.group(3).lower()
            
            results.append({
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "raw_text": match.group(0)
            })
        return results

    def compare_khoan_texts(self, old_text: str, new_text: str) -> Dict[str, Any]:
        """
        So sánh nội dung cũ và mới của một Khoản.
        (Sử dụng cho trường hợp biết chắc 2 khoản này map với nhau nhưng text thay đổi).
        """
        # Trạng thái cơ bản
        status = "unchanged"
        if not old_text and new_text:
            status = "added"
        elif old_text and not new_text:
            status = "deleted"
        elif old_text != new_text:
            status = "modified"

        # TODO: Tích hợp difflib hoặc gọi LLM để diff cấu trúc 
        # Ví dụ: Mức phạt tăng từ 2tr lên 5tr
        
        return {
            "method": "similarity",
            "old_text": old_text,
            "new_text": new_text,
            "status": status,
            "hunks": [] # Chứa các đoạn text cụ thể bị đổi (vd: [{"type": "replace", "old": "2 triệu", "new": "5 triệu"}])
        }

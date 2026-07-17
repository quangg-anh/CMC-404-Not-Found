import hashlib
import re
import unicodedata

def remove_accents(input_str: str) -> str:
    """
    Loại bỏ dấu tiếng Việt để chuẩn hóa chuỗi.
    Ví dụ: 'NĐ-CP' -> 'ND-CP', 'QĐ' -> 'QD'
    """
    # Thay thế thủ công ký tự Đ/đ vì hàm normalize NFKD không xử lý triệt để ký tự này
    s = re.sub(r'[đĐ]', 'D', input_str)
    # Chuẩn hóa Unicode phân rã các ký tự có dấu và xóa chúng
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    return s.upper()

def normalize_so_hieu(so_hieu: str) -> str:
    """
    Chuẩn hóa số hiệu văn bản pháp luật.
    Xóa khoảng trắng dư thừa, chuẩn hóa dấu gạch ngang, dấu gạch chéo và loại bỏ dấu tiếng Việt.
    Ví dụ: " 15 /2020 /NĐ - CP " -> "15/2020/ND-CP"
    """
    if not so_hieu:
        return ""
    
    # Cắt khoảng trắng hai đầu
    s = so_hieu.strip()
    
    # Xóa khoảng trắng xung quanh các dấu '/' và '-'
    s = re.sub(r'\s*/\s*', '/', s)
    s = re.sub(r'\s*-\s*', '-', s)
    
    # Bỏ dấu tiếng Việt, viết hoa toàn bộ
    s = remove_accents(s)
    
    # Xóa mọi khoảng trắng còn lại nếu có
    s = s.replace(" ", "")
    
    return s

def generate_van_ban_id(so_hieu_norm: str, ngay_ban_hanh: str) -> str:
    """
    Sinh ID duy nhất cho Văn Bản Pháp Luật.
    Dựa trên quy ước Data/SYSTEM_DATA.md: vb_id = hash(so_hieu_norm + ngay_ban_hanh)
    """
    raw_str = f"{so_hieu_norm}_{ngay_ban_hanh}"
    # Trả về 16 ký tự đầu của mã băm SHA-256 để làm ID tối ưu
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()[:16]

def generate_khoan_id(so_hieu_norm: str, dieu: str | int, khoan: str | int) -> str:
    """
    Sinh Canonical ID cho một 'Khoản'.
    Dựa trên quy ước Data/SYSTEM_DATA.md: {so_hieu_norm}::D{dieu}.K{khoan}
    Ví dụ: "15/2020/ND-CP::D1.K2"
    """
    return f"{so_hieu_norm}::D{dieu}.K{khoan}"

def generate_diem_id(khoan_id: str, ky_hieu_diem: str) -> str:
    """
    Sinh Canonical ID cho một 'Điểm'.
    Dựa trên quy ước Data/SYSTEM_DATA.md: {khoan_id}.P{ky_hieu}
    Ví dụ: ky_hieu_diem="a)" hoặc "a", khoan_id="15/2020/ND-CP::D1.K2"
    -> "15/2020/ND-CP::D1.K2.Pa"
    """
    # Làm sạch ký hiệu điểm (bỏ dấu ngoặc ')' nếu có)
    ky_hieu_clean = str(ky_hieu_diem).replace(')', '').strip().lower()
    return f"{khoan_id}.P{ky_hieu_clean}"

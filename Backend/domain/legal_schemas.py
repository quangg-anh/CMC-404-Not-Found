from pydantic import BaseModel, Field
from typing import List

class ThucThePhapLy(BaseModel):
    mo_ta: str = Field(..., description="Mô tả nguyên văn hoặc tóm tắt thực thể pháp lý")
    nguon_khoan_id: str = Field(None, description="Canonical ID của Khoản chứa thực thể này")

class ChuThe(ThucThePhapLy):
    pass

class NghiaVu(ThucThePhapLy):
    pass

class QuyenLoi(ThucThePhapLy):
    pass

class HanhViCam(ThucThePhapLy):
    pass

class ThoiHan(ThucThePhapLy):
    pass

class CheTai(ThucThePhapLy):
    pass

class KhoanEntities(BaseModel):
    """
    Schema cứng (Schema-locked) để ép LLM trả về đúng định dạng JSON 
    chứa các thực thể pháp lý được bóc tách từ một Khoản.
    """
    chu_the: List[ChuThe] = Field(default_factory=list, description="Danh sách các đối tượng áp dụng")
    nghia_vu: List[NghiaVu] = Field(default_factory=list, description="Những việc bắt buộc phải làm")
    quyen_loi: List[QuyenLoi] = Field(default_factory=list, description="Những lợi ích được hưởng")
    hanh_vi_cam: List[HanhViCam] = Field(default_factory=list, description="Những việc không được phép làm")
    thoi_han: List[ThoiHan] = Field(default_factory=list, description="Mốc thời gian cụ thể (nếu có)")
    che_tai: List[CheTai] = Field(default_factory=list, description="Hình thức xử phạt (nếu có)")

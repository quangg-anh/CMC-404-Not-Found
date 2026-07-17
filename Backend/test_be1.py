import sys
import os

# Thêm thư mục Backend vào sys.path để Python có thể import các module theo cấu trúc chuẩn
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

def run_tests():
    print("--- KIỂM TRA IMPORT MODULES ---")
    try:
        from app.pipelines.legal.crawler import LegalCrawler
        from app.pipelines.legal.ingest import LegalIngester
        from app.pipelines.legal.normalize import normalize_so_hieu, generate_khoan_id
        from app.pipelines.legal.parser import LegalParser
        from app.pipelines.legal.extractor import LegalExtractor
        from app.pipelines.legal.version_diff import VersionDiff
        from domain.legal_schemas import KhoanEntities
        from workers.legal_jobs import legal_ingest
        print("[OK] Tất cả các file đã được compile và import thành công (không có SyntaxError)!\n")
    except Exception as e:
        print("[LỖI IMPORT] Có lỗi xảy ra khi load các file:")
        import traceback
        traceback.print_exc()
        return

    print("--- KIỂM TRA LOGIC CƠ BẢN ---")
    try:
        # 1. Test Normalize
        norm = normalize_so_hieu(" 15 /2020 /NĐ - CP ")
        assert norm == "15/2020/ND-CP", f"Lỗi normalize: {norm}"
        print("[OK] normalize.py hoạt động chuẩn xác.")

        # 2. Test Parser State Machine
        parser = LegalParser()
        sample_text = """
Điều 1. Phạm vi điều chỉnh
1. Nghị định này quy định về vấn đề X.
a) Điểm a quy định chi tiết.
b) Điểm b quy định thêm.
Đây là text bị trôi nổi sẽ được cộng dồn vào điểm b.
2. Khoản 2 quy định vấn đề Y.
Điều 2. Hiệu lực thi hành
Nghị định có hiệu lực từ hôm nay.
        """
        tree, needs_review = parser.parse_text(sample_text)
        
        # Verify cấu trúc cây
        assert len(tree) == 2, "Phải có đúng 2 Điều"
        assert tree[0]["so"] == "1", "Điều đầu tiên phải là số 1"
        assert len(tree[0]["khoan_list"]) == 2, "Điều 1 phải có 2 Khoản"
        assert len(tree[0]["khoan_list"][0]["diem_list"]) == 2, "Khoản 1 phải có 2 Điểm"
        assert "cộng dồn vào điểm b" in tree[0]["khoan_list"][0]["diem_list"][1]["noi_dung"], "Lỗi nối text (multi-line) vào điểm b"
        assert "Nghị định có hiệu lực" in tree[1]["noi_dung"], "Lỗi nối text vào Điều 2"
        
        print("[OK] parser.py (Regex State Machine) bóc tách chính xác Điều-Khoản-Điểm.\n")
        
        print("🎉 TẤT CẢ MODULE BE1 ĐÃ VƯỢT QUA BÀI TEST CƠ BẢN!")
        
    except AssertionError as ae:
        print("[LỖI LOGIC] Test thất bại:")
        print(ae)
    except Exception as e:
        print("[LỖI RUNTIME] Lỗi không lường trước:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_tests()

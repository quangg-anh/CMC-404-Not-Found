"""Topic relevance gating: no off-topic citations; keep only on-topic grounds."""

from app.schemas import CandidateKhoan
from app.services.qa_service import QAService
from be2_service import _answer_says_insufficient, _select_context


def test_filters_fee_clauses_for_alcohol_question():
    q = "Mức phạt nồng độ cồn là bao nhiêu?"
    fee = CandidateKhoan(
        khoan_id="02/2026/ND-CP::D5.K3",
        noi_dung="Mức phạt trung bình được tính bằng trung bình cộng của mức phạt tối thiểu và mức phạt tối đa.",
        score=0.9,
    )
    alcohol = CandidateKhoan(
        khoan_id="100/2019/ND-CP::D5.K1",
        noi_dung="Người điều khiển xe ô tô mà trong máu hoặc hơi thở có nồng độ cồn vượt quá 50 miligam bị phạt tiền.",
        score=0.8,
    )
    kept = QAService._filter_relevant_candidates([fee, alcohol], q)
    assert [c.khoan_id for c in kept] == ["100/2019/ND-CP::D5.K1"]


def test_insufficient_answer_clears_citations():
    q = "Mức phạt nồng độ cồn là bao nhiêu?"
    ans = "Ngữ cảnh được cung cấp không quy định về mức phạt nồng độ cồn."
    assert QAService._answer_says_insufficient(ans)
    narrow = QAService._narrow_citations(
        ans,
        [{"khoan_id": "02/2026/ND-CP::D5.K3", "quote": "Mức phạt trung bình..."}],
        q,
    )
    assert narrow == []


def test_partial_coverage_keeps_citations():
    """Admin bug: 'chưa đủ toàn bộ nội dung' must NOT wipe verified citations."""
    q = "07/2017/QD-TTG nói về nội dung gì"
    ans = (
        "**Kết luận ngắn:** 07/2017/QD-TTG quy định nguyên tắc bảo đảm trong thu giá dịch vụ.\n"
        "**Nội dung có căn cứ:**\n"
        "- Minh bạch [07/2017/QD-TTG::D4.K5]\n"
        "**Thiếu gì/giới hạn:** Chưa đủ căn cứ xác định toàn bộ nội dung văn bản, chỉ có trích đoạn Điều 4."
    )
    assert not QAService._answer_says_insufficient(ans)
    assert not _answer_says_insufficient(ans)
    kept = QAService._narrow_citations(
        ans,
        [
            {"khoan_id": "07/2017/QD-TTG::D4.K5", "quote": "Minh bạch thu giá"},
            {"khoan_id": "07/2017/QD-TTG::D4.K2", "quote": "Quyền thụ hưởng"},
        ],
        q,
        max_n=5,
    )
    assert len(kept) == 2
    assert all(c["khoan_id"].startswith("07/2017/QD-TTG") for c in kept)


def test_be2_drops_off_topic_context():
    q = "Mức phạt nồng độ cồn là bao nhiêu?"
    fee = ("02/2026/ND-CP::D5.K3", "Mức phạt trung bình được tính bằng trung bình cộng.")
    alcohol = (
        "100/2019/ND-CP::D5.K1",
        "Trong máu hoặc hơi thở có nồng độ cồn vượt quá mức quy định bị phạt tiền.",
    )
    assert _select_context([fee], q) == []
    assert [k for k, _ in _select_context([fee, alcohol], q)] == ["100/2019/ND-CP::D5.K1"]
    assert _answer_says_insufficient("Ngữ cảnh không quy định về mức phạt nồng độ cồn.")


def test_be2_keeps_document_id_context():
    q = "07/2017/QD-TTG nói về nội dung gì"
    ctx = [
        ("07/2017/QD-TTG::D4.K5", "Minh bạch thu giá dịch vụ sử dụng đường bộ."),
        ("07/2017/QD-TTG::D4.K2", "Bảo đảm quyền thụ hưởng của nhà đầu tư."),
    ]
    assert [k for k, _ in _select_context(ctx, q)] == [
        "07/2017/QD-TTG::D4.K5",
        "07/2017/QD-TTG::D4.K2",
    ]

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

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.domain.citation_contract import (
    CitationAnswerDraftV2,
    CitationContractV2,
    QAAnswerStatus,
)
from app.domain.legal_retrieval import RetrievalProfile
from app.exceptions import ValidationError
from app.services import qa_topic


logger = logging.getLogger(__name__)


class LegalQAV2Service:
    """Feature-flagged legal QA path that emits only CitationContractV2."""

    def __init__(
        self,
        retrieval_service: Any,
        citation_validator: Any,
        llm_router: Any,
    ) -> None:
        self.retrieval = retrieval_service
        self.validator = citation_validator
        self.router = llm_router

    @staticmethod
    def _refused(as_of: date, reason_code: str) -> CitationContractV2:
        return CitationContractV2(
            status=QAAnswerStatus.REFUSED,
            as_of=as_of,
            reason_code=reason_code,
        )

    @staticmethod
    def _as_of(value: date | str | None) -> date:
        if value is None:
            return date.today()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value).strip())
        except ValueError as exc:
            raise ValidationError("as_of must be an ISO date (YYYY-MM-DD)") from exc

    @staticmethod
    def _context_line(candidate: Any) -> str:
        provision = candidate.provision
        coordinate = f"Điều {provision.article}"
        if provision.clause is not None:
            coordinate += f", Khoản {provision.clause}"
        if provision.point is not None:
            coordinate += f", Điểm {provision.point}"
        text = " ".join(provision.text.split())
        return (
            f"[node_id={provision.provision_id}] "
            f"[{provision.source_vb_id}; {coordinate}; "
            f"effective_from={provision.effective_from}; "
            f"effective_to={provision.effective_to}] "
            f"{text[:2000]}"
        )

    async def answer(
        self,
        question: str,
        *,
        audience: str,
        as_of: date | str | None = None,
    ) -> CitationContractV2:
        query = " ".join(str(question or "").split())
        if not query:
            raise ValidationError("question is required")
        if audience not in {"admin", "citizen"}:
            raise ValidationError("audience must be admin or citizen")
        requested_date = self._as_of(as_of)

        if qa_topic.is_non_legal_meta_question(query):
            return self._refused(requested_date, "non_legal_meta_question")
        if self.retrieval is None:
            return self._refused(requested_date, "legal_retrieval_unavailable")
        if self.router is None:
            return self._refused(requested_date, "llm_router_unavailable")
        if self.validator is None:
            return self._refused(requested_date, "canonical_validator_unavailable")

        try:
            retrieved = await self.retrieval.retrieve(
                query,
                as_of=requested_date,
                audience=audience,
                profile=RetrievalProfile.HYBRID_GRAPH_RERANK,
                limit=8,
            )
        except Exception as exc:
            logger.warning("Citation v2 retrieval failed: %s", exc)
            return self._refused(requested_date, "legal_retrieval_unavailable")
        if not retrieved.items:
            return self._refused(requested_date, "insufficient_legal_basis")

        context = "\n".join(self._context_line(candidate) for candidate in retrieved.items)
        prompt = (
            "retrieved_context:\n"
            f"{context}\n\n"
            f"Câu hỏi: {query}\n"
            f"Ngày áp dụng: {requested_date.isoformat()}\n\n"
            "Chỉ trả lời bằng dữ liệu trong retrieved_context. Mỗi câu khẳng định pháp lý "
            "có số tiền, tỷ lệ, thời hạn, nghĩa vụ, điều kiện, hành vi cấm hoặc chế tài phải "
            "xuất hiện nguyên văn trong một claim. Mỗi claim phải dùng citation_ids; mỗi "
            "citation phải dùng đúng node_id đã cung cấp và quote phải là chuỗi con nguyên "
            "văn của nội dung node. Mapping claim/citation phải hai chiều. Không tự tạo "
            "Điều, Khoản, Điểm, số hiệu, node_id hoặc quote.\n"
            "JSON fields: answer; claims[{claim_id,text,citation_ids}]; "
            "citations[{citation_id,node_id,quote,supports_claim_ids}]."
        )
        try:
            draft = await self.router.complete(
                task="qa",
                prompt=prompt,
                schema=CitationAnswerDraftV2,
                complexity="medium",
            )
        except Exception as exc:
            logger.warning("Citation v2 LLM generation failed: %s", exc)
            return self._refused(requested_date, "llm_generation_unavailable")
        if draft.get("needs_review") or draft.get("status") == "needs_review":
            return self._refused(requested_date, "invalid_model_output")

        allowed_node_ids = {
            candidate.provision.provision_id for candidate in retrieved.items
        }
        outcome = await self.validator.validate_answer_draft(
            draft,
            as_of=requested_date,
            audience=audience,
            allowed_node_ids=allowed_node_ids,
        )
        if outcome.issues:
            logger.info(
                "Citation v2 refused",
                extra={
                    "reason_code": outcome.contract.reason_code,
                    "issue_codes": [issue.code for issue in outcome.issues],
                },
            )
        return outcome.contract

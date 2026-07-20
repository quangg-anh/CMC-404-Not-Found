from __future__ import annotations

import re
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError

from app.domain.citation_contract import (
    AnswerClaimV2,
    CitationAnswerDraftV2,
    CitationContractV2,
    CitationV2,
    ClaimSupportStatus,
    QAAnswerStatus,
)
from app.domain.legal_provision import LegalProvisionVersion, legal_text_checksum


_MATERIAL_CLAIM_RE = re.compile(
    r"\d|%|"
    r"\b(?:tiền|mức|ngưỡng|triệu|tỷ|đồng|thời hạn|ngày|tháng|năm|tỷ lệ|phạt|"
    r"chế tài|cấm|không được|bắt buộc|nghĩa vụ|điều|khoản|điểm)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


class CitationValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    item_id: str | None = None
    message: str = Field(min_length=1)


class CitationValidationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: CitationContractV2
    issues: list[CitationValidationIssue] = Field(default_factory=list)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(_normalize(text)) if len(token) > 1}


def _claim_matches_segment(claim: str, segment: str) -> bool:
    left = _normalize(claim).casefold()
    right = _normalize(segment).casefold()
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    segment_tokens = _tokens(right)
    if not segment_tokens:
        return False
    return len(_tokens(left) & segment_tokens) / len(segment_tokens) >= 0.8


def _answer_segments(answer: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+|\n+", answer or "")
    cleaned = [
        re.sub(r"^(?:[#>*•\-]+\s*|\d+[.)]\s*)", "", part).strip()
        for part in parts
    ]
    return [part for part in cleaned if len(part) >= 8]


class CanonicalCitationValidator:
    """Build Citation v2 only from exact, date-valid Neo4j provision versions."""

    def __init__(
        self,
        temporal_service: Any,
        nli: Any,
        *,
        entailment_threshold: float | None = None,
    ) -> None:
        self.temporal = temporal_service
        self.nli = nli
        configured = getattr(getattr(nli, "config", None), "nli_confidence_threshold", 0.7)
        self.entailment_threshold = float(
            configured if entailment_threshold is None else entailment_threshold
        )

    @staticmethod
    def _refused(
        as_of: date,
        code: str,
        *,
        item_id: str | None = None,
        message: str,
        issues: list[CitationValidationIssue] | None = None,
    ) -> CitationValidationOutcome:
        all_issues = list(issues or [])
        all_issues.append(
            CitationValidationIssue(code=code, item_id=item_id, message=message)
        )
        return CitationValidationOutcome(
            contract=CitationContractV2(
                status=QAAnswerStatus.REFUSED,
                as_of=as_of,
                reason_code=code,
            ),
            issues=all_issues,
        )

    @staticmethod
    def _validate_answer_claim_coverage(
        draft: CitationAnswerDraftV2,
    ) -> CitationValidationIssue | None:
        for claim in draft.claims:
            if not _claim_matches_segment(claim.text, draft.answer):
                return CitationValidationIssue(
                    code="claim_not_in_answer",
                    item_id=claim.claim_id,
                    message="Claim text is not represented in the answer.",
                )
        for segment in _answer_segments(draft.answer):
            if not _MATERIAL_CLAIM_RE.search(segment):
                continue
            if not any(_claim_matches_segment(claim.text, segment) for claim in draft.claims):
                return CitationValidationIssue(
                    code="unmapped_material_claim",
                    message="A material answer statement has no claim-level citation mapping.",
                )
        return None

    async def validate_answer_draft(
        self,
        draft: CitationAnswerDraftV2 | dict[str, Any],
        *,
        as_of: date,
        audience: str,
        allowed_node_ids: set[str] | None = None,
    ) -> CitationValidationOutcome:
        try:
            parsed = (
                draft
                if isinstance(draft, CitationAnswerDraftV2)
                else CitationAnswerDraftV2.model_validate(draft)
            )
        except PydanticValidationError as exc:
            return self._refused(
                as_of,
                "invalid_citation_draft",
                message=f"Citation draft failed schema validation: {exc}",
            )

        coverage_issue = self._validate_answer_claim_coverage(parsed)
        if coverage_issue is not None:
            return self._refused(
                as_of,
                coverage_issue.code,
                item_id=coverage_issue.item_id,
                message=coverage_issue.message,
            )

        requested_node_ids = list(
            dict.fromkeys(citation.node_id for citation in parsed.citations)
        )
        if allowed_node_ids is not None:
            outside = [node_id for node_id in requested_node_ids if node_id not in allowed_node_ids]
            if outside:
                return self._refused(
                    as_of,
                    "citation_node_not_retrieved",
                    item_id=outside[0],
                    message="Citation node was not present in canonical retrieval candidates.",
                )

        try:
            provisions = await self.temporal.hydrate_exact_versions(
                requested_node_ids,
                as_of=as_of,
                audience=audience,
            )
        except Exception as exc:
            return self._refused(
                as_of,
                "canonical_validation_unavailable",
                message=f"Canonical citation validation failed: {type(exc).__name__}",
            )
        by_id = {provision.provision_id: provision for provision in provisions}
        missing = [node_id for node_id in requested_node_ids if node_id not in by_id]
        if missing:
            return self._refused(
                as_of,
                "citation_node_invalid_for_as_of",
                item_id=missing[0],
                message="Citation node is missing, hidden, or not effective at as_of.",
            )

        citation_drafts = {citation.citation_id: citation for citation in parsed.citations}
        canonical_quotes: dict[str, str] = {}
        for citation in parsed.citations:
            provision = by_id[citation.node_id]
            if legal_text_checksum(provision.text) != provision.text_checksum:
                return self._refused(
                    as_of,
                    "citation_checksum_mismatch",
                    item_id=citation.citation_id,
                    message="Canonical legal text checksum does not match the provision contract.",
                )
            quote = _normalize(citation.quote)
            if quote not in _normalize(provision.text):
                return self._refused(
                    as_of,
                    "citation_quote_mismatch",
                    item_id=citation.citation_id,
                    message="Citation quote is not an exact canonical substring.",
                )
            canonical_quotes[citation.citation_id] = quote

        pair_scores: dict[str, list[float]] = {
            citation.citation_id: [] for citation in parsed.citations
        }
        for claim in parsed.claims:
            for citation_id in claim.citation_ids:
                citation = citation_drafts[citation_id]
                provision = by_id[citation.node_id]
                try:
                    result = await self.nli.nli_pair(
                        premise=provision.text,
                        hypothesis=claim.text,
                    )
                except Exception as exc:
                    return self._refused(
                        as_of,
                        "claim_validation_unavailable",
                        item_id=claim.claim_id,
                        message=f"Claim entailment validation failed: {type(exc).__name__}",
                    )
                raw_label = result.get("label")
                label = getattr(raw_label, "value", raw_label)
                score = max(0.0, min(1.0, float(result.get("score") or 0.0)))
                if (
                    label != "khop"
                    or bool(result.get("needs_review"))
                    or score < self.entailment_threshold
                ):
                    return self._refused(
                        as_of,
                        "claim_not_supported",
                        item_id=claim.claim_id,
                        message=(
                            "A declared claim-citation edge is not decisively entailed "
                            f"(label={label}, score={score:.3f})."
                        ),
                    )
                pair_scores[citation_id].append(score)

        claims = [
            AnswerClaimV2(
                claim_id=claim.claim_id,
                text=claim.text,
                citation_ids=claim.citation_ids,
                support_status=ClaimSupportStatus.ENTAILED,
            )
            for claim in parsed.claims
        ]
        citations: list[CitationV2] = []
        for citation in parsed.citations:
            provision: LegalProvisionVersion = by_id[citation.node_id]
            scores = pair_scores[citation.citation_id]
            citations.append(
                CitationV2(
                    citation_id=citation.citation_id,
                    node_id=provision.provision_id,
                    lineage_id=provision.lineage_id,
                    level=provision.level,
                    document_number=provision.source_vb_id,
                    article=provision.article,
                    clause=provision.clause,
                    point=provision.point,
                    quote=canonical_quotes[citation.citation_id],
                    effective_from=provision.effective_from,
                    effective_to=provision.effective_to,
                    text_checksum=provision.text_checksum,
                    source_checksum=provision.source_checksum,
                    supports_claim_ids=citation.supports_claim_ids,
                    entailment_score=min(scores),
                )
            )

        try:
            contract = CitationContractV2(
                status=QAAnswerStatus.ANSWERED,
                as_of=as_of,
                answer=parsed.answer,
                claims=claims,
                citations=citations,
            )
        except PydanticValidationError as exc:
            return self._refused(
                as_of,
                "citation_contract_invalid",
                message=f"Validated citation contract is inconsistent: {exc}",
            )
        return CitationValidationOutcome(contract=contract)

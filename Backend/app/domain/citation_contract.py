from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.legal_provision import ProvisionLevel, build_version_id, parse_lineage_id


class QAAnswerStatus(StrEnum):
    ANSWERED = "answered"
    REFUSED = "refused"


class ClaimSupportStatus(StrEnum):
    ENTAILED = "entailed"
    UNSUPPORTED = "unsupported"
    NEEDS_REVIEW = "needs_review"


class AnswerClaimDraftV2(BaseModel):
    """Untrusted claim structure proposed by the language model."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    citation_ids: list[str] = Field(min_length=1)


class CitationDraftV2(BaseModel):
    """Untrusted minimal citation pointer proposed by the language model."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    citation_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    supports_claim_ids: list[str] = Field(min_length=1)


class CitationAnswerDraftV2(BaseModel):
    """Strict schema boundary before canonical Neo4j validation."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    answer: str = Field(min_length=1)
    claims: list[AnswerClaimDraftV2] = Field(min_length=1)
    citations: list[CitationDraftV2] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cross_references(self) -> "CitationAnswerDraftV2":
        claim_ids = [claim.claim_id for claim in self.claims]
        citation_ids = [citation.citation_id for citation in self.citations]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("draft claim_id values must be unique")
        if len(set(citation_ids)) != len(citation_ids):
            raise ValueError("draft citation_id values must be unique")

        claim_id_set = set(claim_ids)
        citation_id_set = set(citation_ids)
        citations_by_id = {citation.citation_id: citation for citation in self.citations}
        claims_by_id = {claim.claim_id: claim for claim in self.claims}
        for claim in self.claims:
            if len(set(claim.citation_ids)) != len(claim.citation_ids):
                raise ValueError("draft claim citation_ids must be unique")
            unknown = set(claim.citation_ids) - citation_id_set
            if unknown:
                raise ValueError(f"draft claim references unknown citations: {sorted(unknown)}")
            for citation_id in claim.citation_ids:
                if claim.claim_id not in citations_by_id[citation_id].supports_claim_ids:
                    raise ValueError("draft claim/citation mapping must be reciprocal")
        for citation in self.citations:
            if len(set(citation.supports_claim_ids)) != len(citation.supports_claim_ids):
                raise ValueError("draft citation supports_claim_ids must be unique")
            unknown = set(citation.supports_claim_ids) - claim_id_set
            if unknown:
                raise ValueError(f"draft citation references unknown claims: {sorted(unknown)}")
            for claim_id in citation.supports_claim_ids:
                if citation.citation_id not in claims_by_id[claim_id].citation_ids:
                    raise ValueError("draft citation/claim mapping must be reciprocal")
        return self


class AnswerClaimV2(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    citation_ids: list[str] = Field(min_length=1)
    support_status: ClaimSupportStatus


class CitationV2(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    citation_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)
    level: ProvisionLevel
    document_number: str = Field(min_length=1)
    article: str = Field(min_length=1)
    clause: str | None = None
    point: str | None = None
    quote: str = Field(min_length=1)
    effective_from: date
    effective_to: date | None = None
    text_checksum: str = Field(min_length=64, max_length=64)
    source_checksum: str | None = Field(default=None, min_length=64, max_length=64)
    supports_claim_ids: list[str] = Field(min_length=1)
    entailment_score: float = Field(ge=0, le=1)
    validation_source: Literal["neo4j"] = "neo4j"

    @model_validator(mode="after")
    def validate_citation(self) -> "CitationV2":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        for field, checksum in (
            ("text_checksum", self.text_checksum),
            ("source_checksum", self.source_checksum),
        ):
            if checksum is None:
                continue
            try:
                int(checksum, 16)
            except ValueError as exc:
                raise ValueError(f"{field} must be a SHA-256 hex digest") from exc
        coordinates = parse_lineage_id(self.lineage_id)
        if (
            self.article != coordinates.article
            or self.clause != coordinates.clause
            or self.point != coordinates.point
        ):
            raise ValueError("citation coordinates do not match lineage_id")
        expected_node_id = build_version_id(
            self.lineage_id,
            self.effective_from,
            self.text_checksum,
        )
        if self.node_id != expected_node_id:
            raise ValueError("citation node_id does not match version identity")
        if len(set(self.supports_claim_ids)) != len(self.supports_claim_ids):
            raise ValueError("supports_claim_ids must be unique")
        return self


class CitationContractV2(BaseModel):
    """Strict claim-level response contract for grounded legal QA."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    status: QAAnswerStatus
    as_of: date
    answer: str | None = None
    claims: list[AnswerClaimV2] = Field(default_factory=list)
    citations: list[CitationV2] = Field(default_factory=list)
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_cross_references(self) -> "CitationContractV2":
        claim_ids = [claim.claim_id for claim in self.claims]
        citation_ids = [citation.citation_id for citation in self.citations]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("claim_id values must be unique")
        if len(set(citation_ids)) != len(citation_ids):
            raise ValueError("citation_id values must be unique")

        if self.status == QAAnswerStatus.REFUSED:
            if self.answer is not None or self.claims or self.citations or not self.reason_code:
                raise ValueError("refused response requires reason_code and no answer/claims/citations")
            return self

        if not self.answer or not self.claims or not self.citations:
            raise ValueError("answered response requires answer, claims, and citations")
        if self.reason_code is not None:
            raise ValueError("answered response cannot include reason_code")

        claim_id_set = set(claim_ids)
        citation_id_set = set(citation_ids)
        citations_by_id = {citation.citation_id: citation for citation in self.citations}
        claims_by_id = {claim.claim_id: claim for claim in self.claims}
        for claim in self.claims:
            if claim.support_status != ClaimSupportStatus.ENTAILED:
                raise ValueError("answered claims must be entailed")
            if len(set(claim.citation_ids)) != len(claim.citation_ids):
                raise ValueError("claim citation_ids must be unique")
            unknown = set(claim.citation_ids) - citation_id_set
            if unknown:
                raise ValueError(f"claim references unknown citations: {sorted(unknown)}")
            for citation_id in claim.citation_ids:
                if claim.claim_id not in citations_by_id[citation_id].supports_claim_ids:
                    raise ValueError("claim/citation support mapping must be reciprocal")

        for citation in self.citations:
            if not (
                citation.effective_from <= self.as_of
                and (citation.effective_to is None or self.as_of < citation.effective_to)
            ):
                raise ValueError("citation is not effective at contract as_of")
            unknown = set(citation.supports_claim_ids) - claim_id_set
            if unknown:
                raise ValueError(f"citation references unknown claims: {sorted(unknown)}")
            for claim_id in citation.supports_claim_ids:
                if citation.citation_id not in claims_by_id[claim_id].citation_ids:
                    raise ValueError("citation/claim support mapping must be reciprocal")
        return self
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.legal_provision import ProvisionLevel


class AmendmentAction(StrEnum):
    AMEND = "amend"
    ADD = "add"
    REPLACE = "replace"
    REPEAL = "repeal"


class LegalChangeType(StrEnum):
    UNCHANGED = "UNCHANGED"
    REWORDED = "REWORDED"
    TIGHTENED = "TIGHTENED"
    LOOSENED = "LOOSENED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    SPLIT = "SPLIT"
    MERGED = "MERGED"
    UNCERTAIN = "UNCERTAIN"


class AmendmentReviewRoute(StrEnum):
    HUMAN_REVIEW = "human_review"
    MANDATORY_REVIEW = "mandatory_review"


class ExplicitAmendmentReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    reference_id: str = Field(min_length=1)
    action: AmendmentAction
    raw_text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    level: ProvisionLevel | None = None
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    target_lineage_id: str | None = None
    old_phrase: str | None = None
    new_phrase: str | None = None
    multiple_targets: bool = False
    complete_coordinates: bool = False

    @model_validator(mode="after")
    def validate_reference(self) -> "ExplicitAmendmentReference":
        if self.end <= self.start:
            raise ValueError("reference end must be later than start")
        if self.point is not None and self.clause is None:
            raise ValueError("point reference requires clause")
        if self.clause is not None and self.article is None:
            raise ValueError("clause reference requires article")
        if self.level == ProvisionLevel.DIEM and self.point is None:
            raise ValueError("Điểm reference requires point")
        if self.level == ProvisionLevel.KHOAN and self.clause is None:
            raise ValueError("Khoản reference requires clause")
        if self.level == ProvisionLevel.DIEU and self.article is None:
            raise ValueError("Điều reference requires article")
        if (self.old_phrase is None) != (self.new_phrase is None):
            raise ValueError("phrase replacement requires both old_phrase and new_phrase")
        return self


class AmendmentScoreBreakdown(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    explicit_reference: float = Field(ge=0, le=1)
    coordinate_match: float = Field(ge=0, le=1)
    level_match: float = Field(ge=0, le=1)
    lexical_similarity: float = Field(ge=0, le=1)
    numeric_overlap: float = Field(ge=0, le=1)
    legal_term_overlap: float = Field(ge=0, le=1)
    total: float = Field(ge=0, le=1)


class AmendmentDiffHunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["replace", "delete", "insert"]
    old: str
    new: str


class AmendmentMatchPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    match_id: str = Field(min_length=1)
    old_provision_id: str = Field(min_length=1)
    new_provision_id: str = Field(min_length=1)
    lineage_id: str | None = None
    reference_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    score: AmendmentScoreBreakdown
    change_type: LegalChangeType
    review_route: AmendmentReviewRoute
    auto_approve_eligible: Literal[False] = False
    reason_codes: list[str] = Field(default_factory=list)
    diff_hunks: list[AmendmentDiffHunk] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_preview(self) -> "AmendmentMatchPreview":
        if self.old_provision_id == self.new_provision_id:
            raise ValueError("amendment preview cannot pair a node with itself")
        if len(set(self.reference_ids)) != len(self.reference_ids):
            raise ValueError("reference_ids must be unique")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes must be unique")
        if self.change_type in {
            LegalChangeType.SPLIT,
            LegalChangeType.MERGED,
            LegalChangeType.UNCERTAIN,
        } and self.review_route != AmendmentReviewRoute.MANDATORY_REVIEW:
            raise ValueError("ambiguous change types require mandatory review")
        return self


class UnmatchedAmendmentPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    provision_id: str = Field(min_length=1)
    side: Literal["old", "new"]
    change_type: LegalChangeType
    review_route: Literal[AmendmentReviewRoute.MANDATORY_REVIEW] = AmendmentReviewRoute.MANDATORY_REVIEW
    auto_approve_eligible: Literal[False] = False
    reason_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unmatched_change(self) -> "UnmatchedAmendmentPreview":
        expected = LegalChangeType.REMOVED if self.side == "old" else LegalChangeType.ADDED
        if self.change_type != expected:
            raise ValueError(f"{self.side} unmatched provision must be {expected}")
        return self


class AmendmentPreviewResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    mode: Literal["preview"] = "preview"
    commit_allowed: Literal[False] = False
    target_logical_vb_id: str = Field(min_length=1)
    references: list[ExplicitAmendmentReference] = Field(default_factory=list)
    matches: list[AmendmentMatchPreview] = Field(default_factory=list)
    unmatched_old_ids: list[str] = Field(default_factory=list)
    unmatched_new_ids: list[str] = Field(default_factory=list)
    unmatched_changes: list[UnmatchedAmendmentPreview] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> "AmendmentPreviewResult":
        old_ids = [item.old_provision_id for item in self.matches]
        new_ids = [item.new_provision_id for item in self.matches]
        if len(set(old_ids)) != len(old_ids):
            raise ValueError("preview must select at most one match per old provision")
        if len(set(new_ids)) != len(new_ids):
            raise ValueError("preview must select at most one match per new provision")
        if set(old_ids) & set(self.unmatched_old_ids):
            raise ValueError("matched old provisions cannot also be unmatched")
        if set(new_ids) & set(self.unmatched_new_ids):
            raise ValueError("matched new provisions cannot also be unmatched")
        unmatched_change_ids = [item.provision_id for item in self.unmatched_changes]
        if len(set(unmatched_change_ids)) != len(unmatched_change_ids):
            raise ValueError("unmatched_changes provision ids must be unique")
        if set(unmatched_change_ids) != set(self.unmatched_old_ids + self.unmatched_new_ids):
            raise ValueError("unmatched_changes must cover every unmatched provision")
        return self

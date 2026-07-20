from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class NliLabel(StrEnum):
    KHOP = "khop"
    MAU_THUAN = "mau_thuan"
    KHONG_RO = "khong_ro"


class Status(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"


class ContentSourceType(StrEnum):
    NEWS = "news"
    SOCIAL_POST = "social_post"
    VIDEO = "video"
    COMMENT = "comment"
    FORUM = "forum"


class ContentItem(BaseModel):
    """Platform-neutral content contract used by news and social collectors."""

    content_id: str = Field(min_length=1)
    source_type: ContentSourceType
    provider: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    body: str = Field(min_length=1)
    published_at: datetime
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    canonical_url: str | None = None
    title: str | None = None
    author_hash: str | None = None
    content_hash: str = Field(min_length=64, max_length=64)
    engagement: dict[str, Any] = Field(default_factory=dict)
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class SocialPost(BaseModel):
    platform: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    noi_dung: str = Field(min_length=1)
    tac_gia_hash: str | None = None
    url: str | None = None
    thoi_gian: datetime
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TopicResult(BaseModel):
    bai_dang_id: str
    slug: str | None = None
    score: float = Field(ge=0, le=1)
    status: Literal["classified", "needs_review", "unknown"]
    model: str
    version: str | None = None


class CandidateKhoan(BaseModel):
    khoan_id: str = Field(min_length=1)
    noi_dung: str = Field(min_length=1)
    score: float = Field(default=0.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LinkCandidate(BaseModel):
    khoan_id: str
    score: float = Field(ge=0, le=1)
    reason: str | None = None


class LinkPreview(BaseModel):
    bai_dang_id: str
    candidates: list[LinkCandidate]
    proposed_edges: list[LinkCandidate]
    dry_run: bool = True
    status: Literal["ok", "needs_review", "blocked"]
    reasons: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    text: str = Field(min_length=1)
    evidence_span: str = Field(min_length=1)


class NliResult(BaseModel):
    label: NliLabel
    score: float = Field(ge=0, le=1)
    model: str
    needs_review: bool = False


class Citation(BaseModel):
    khoan_id: str
    quote: str = Field(min_length=1)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> "Citation":
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("citation end must be >= start")
        return self


class BriefDraft(BaseModel):
    title: str = Field(min_length=1)
    bullets: list[str] = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    status: Status = Status.DRAFT
    model: str
    audit: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def brief_not_published(cls, value: Status) -> Status:
        if value not in {Status.DRAFT, Status.NEEDS_REVIEW}:
            raise ValueError("BE2 may only create draft or needs_review")
        return value


class SuggestDraft(BaseModel):
    draft_content: str = Field(min_length=1)
    related_alert_ids: list[str] = Field(min_length=1)
    related_chu_de: list[str] = Field(default_factory=list)
    related_khoan_ids: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    disclaimer: str = Field(min_length=1)
    status: Status = Status.DRAFT
    audit: dict[str, Any] = Field(default_factory=dict)


class JobEnvelope(BaseModel):
    job_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class JobResult(BaseModel):
    job_id: str
    status: Literal["success", "failed", "needs_review", "skipped"]
    data: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None

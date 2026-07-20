from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProvisionLevel(StrEnum):
    DIEU = "dieu"
    KHOAN = "khoan"
    DIEM = "diem"


class ProvisionReviewStatus(StrEnum):
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"


def canonicalize_legal_text(text: str) -> str:
    """Normalize insignificant whitespace without changing legal characters or casing."""
    return " ".join((text or "").split())


def legal_text_checksum(text: str) -> str:
    canonical = canonicalize_legal_text(text)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_lineage_id(
    logical_vb_id: str,
    article: str | int,
    clause: str | int | None = None,
    point: str | None = None,
) -> str:
    """Build the stable logical identity of one Điều/Khoản/Điểm across versions."""
    document = str(logical_vb_id).strip()
    article_value = str(article).strip()
    if not document or not article_value:
        raise ValueError("logical_vb_id and article are required")
    lineage_id = f"{document}::D{article_value}"
    if clause is not None:
        clause_value = str(clause).strip()
        if not clause_value:
            raise ValueError("clause cannot be blank")
        lineage_id += f".K{clause_value}"
    if point is not None:
        if clause is None:
            raise ValueError("point requires clause")
        point_value = str(point).replace(")", "").strip().lower()
        if not point_value:
            raise ValueError("point cannot be blank")
        lineage_id += f".P{point_value}"
    return lineage_id


@dataclass(frozen=True)
class LegalCoordinates:
    logical_vb_id: str
    article: str
    clause: str | None = None
    point: str | None = None


_LINEAGE_PATTERN = re.compile(
    r"^(?P<document>.+)::D(?P<article>[^.]+)"
    r"(?:\.K(?P<clause>[^.]+))?"
    r"(?:\.P(?P<point>[^.]+))?$"
)


def parse_lineage_id(lineage_id: str) -> LegalCoordinates:
    """Parse coordinates derived by ``build_lineage_id`` without losing slashes in document IDs."""
    value = str(lineage_id or "").strip()
    match = _LINEAGE_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("invalid legal lineage_id")
    clause = match.group("clause")
    point = match.group("point")
    if point is not None and clause is None:
        raise ValueError("point lineage requires clause")
    return LegalCoordinates(
        logical_vb_id=match.group("document"),
        article=match.group("article"),
        clause=clause,
        point=point,
    )

def build_version_id(lineage_id: str, effective_from: date, text_checksum: str) -> str:
    """Build a deterministic physical ID for an immutable provision version."""
    lineage = str(lineage_id).strip()
    checksum = str(text_checksum).strip().lower()
    if not lineage:
        raise ValueError("lineage_id is required")
    if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
        raise ValueError("text_checksum must be a SHA-256 hex digest")
    return f"{lineage}@{effective_from.isoformat()}#{checksum[:12]}"


class LegalProvisionVersion(BaseModel):
    """Immutable physical version of one legal provision in a temporal lineage."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    provision_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)
    parent_lineage_id: str | None = None
    level: ProvisionLevel
    version_no: int = Field(ge=1)

    source_vb_id: str = Field(min_length=1)
    logical_vb_id: str = Field(min_length=1)
    article: str = Field(min_length=1)
    clause: str | None = None
    point: str | None = None

    text: str = Field(min_length=1)
    effective_from: date
    effective_to: date | None = None
    text_checksum: str = Field(min_length=64, max_length=64)
    source_checksum: str | None = Field(default=None, min_length=64, max_length=64)

    visibility: Literal["public", "internal"] = "public"
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    review_status: ProvisionReviewStatus = ProvisionReviewStatus.APPROVED

    @model_validator(mode="after")
    def validate_temporal_and_structure(self) -> "LegalProvisionVersion":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        if self.text_checksum.lower() != legal_text_checksum(self.text):
            raise ValueError("text_checksum does not match canonical text")
        if self.source_checksum is not None:
            try:
                int(self.source_checksum, 16)
            except ValueError as exc:
                raise ValueError("source_checksum must be a SHA-256 hex digest") from exc

        expected_lineage = build_lineage_id(
            self.logical_vb_id,
            self.article,
            self.clause,
            self.point,
        )
        if self.lineage_id != expected_lineage:
            raise ValueError("lineage_id does not match legal coordinates")
        expected_version_id = build_version_id(
            self.lineage_id,
            self.effective_from,
            self.text_checksum,
        )
        if self.provision_id != expected_version_id:
            raise ValueError("provision_id does not match lineage, date, and checksum")

        if self.level == ProvisionLevel.DIEU:
            if self.clause is not None or self.point is not None or self.parent_lineage_id is not None:
                raise ValueError("Điều cannot have clause, point, or parent_lineage_id")
        elif self.level == ProvisionLevel.KHOAN:
            if self.clause is None or self.point is not None:
                raise ValueError("Khoản requires clause and cannot have point")
            expected_parent = build_lineage_id(self.logical_vb_id, self.article)
            if self.parent_lineage_id != expected_parent:
                raise ValueError("Khoản parent_lineage_id must reference its Điều")
        else:
            if self.clause is None or self.point is None:
                raise ValueError("Điểm requires clause and point")
            expected_parent = build_lineage_id(self.logical_vb_id, self.article, self.clause)
            if self.parent_lineage_id != expected_parent:
                raise ValueError("Điểm parent_lineage_id must reference its Khoản")
        return self

    def is_effective_on(self, as_of: date) -> bool:
        return self.effective_from <= as_of and (
            self.effective_to is None or as_of < self.effective_to
        )


def build_provision_version(
    *,
    logical_vb_id: str,
    source_vb_id: str,
    level: ProvisionLevel,
    article: str | int,
    text: str,
    effective_from: date,
    version_no: int = 1,
    clause: str | int | None = None,
    point: str | None = None,
    effective_to: date | None = None,
    source_checksum: str | None = None,
    visibility: Literal["public", "internal"] = "public",
    review_status: ProvisionReviewStatus = ProvisionReviewStatus.APPROVED,
) -> LegalProvisionVersion:
    """Create a validated version and derive all deterministic identity fields."""
    lineage_id = build_lineage_id(logical_vb_id, article, clause, point)
    checksum = legal_text_checksum(text)
    if level == ProvisionLevel.DIEU:
        parent_lineage_id = None
    elif level == ProvisionLevel.KHOAN:
        parent_lineage_id = build_lineage_id(logical_vb_id, article)
    else:
        parent_lineage_id = build_lineage_id(logical_vb_id, article, clause)
    return LegalProvisionVersion(
        provision_id=build_version_id(lineage_id, effective_from, checksum),
        lineage_id=lineage_id,
        parent_lineage_id=parent_lineage_id,
        level=level,
        version_no=version_no,
        source_vb_id=source_vb_id,
        logical_vb_id=logical_vb_id,
        article=str(article),
        clause=str(clause) if clause is not None else None,
        point=str(point).replace(")", "").strip().lower() if point is not None else None,
        text=canonicalize_legal_text(text),
        effective_from=effective_from,
        effective_to=effective_to,
        text_checksum=checksum,
        source_checksum=source_checksum,
        visibility=visibility,
        review_status=review_status,
    )

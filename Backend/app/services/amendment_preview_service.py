from __future__ import annotations

from typing import Any

from app.domain.amendment import AmendmentPreviewResult
from app.exceptions import ValidationError
from app.pipelines.legal.amendment_matcher import AmendmentMatcher
from app.pipelines.legal.amendment_parser import AmendmentParser


class AmendmentPreviewService:
    """Canonical, read-only amendment analysis. It never commits graph changes."""

    def __init__(
        self,
        temporal_law_service: Any,
        *,
        parser: AmendmentParser | None = None,
        matcher: AmendmentMatcher | None = None,
    ) -> None:
        self.temporal = temporal_law_service
        self.parser = parser or AmendmentParser()
        self.matcher = matcher or AmendmentMatcher()

    async def preview(
        self,
        *,
        amendment_text: str,
        old_provision_ids: list[str],
        new_provision_ids: list[str],
        target_logical_vb_id: str | None = None,
    ) -> AmendmentPreviewResult:
        old_ids = list(dict.fromkeys(str(item).strip() for item in old_provision_ids if str(item).strip()))
        new_ids = list(dict.fromkeys(str(item).strip() for item in new_provision_ids if str(item).strip()))
        if not old_ids:
            raise ValidationError("old_provision_ids must not be empty")
        if not new_ids:
            raise ValidationError("new_provision_ids must not be empty")
        overlap = sorted(set(old_ids) & set(new_ids))
        if overlap:
            raise ValidationError(
                "old and new candidates must be different physical versions",
                details={"overlapping_provision_ids": overlap},
            )
        if self.temporal is None:
            raise ValidationError("temporal law service is required")

        old_versions = await self.temporal.load_versions_by_ids(old_ids, audience="admin")
        new_versions = await self.temporal.load_versions_by_ids(new_ids, audience="admin")
        old_documents = {item.logical_vb_id for item in old_versions}
        requested_document = str(target_logical_vb_id or "").strip() or None
        if requested_document is None:
            if len(old_documents) != 1:
                raise ValidationError(
                    "target_logical_vb_id is required when old candidates span documents",
                    details={"logical_vb_ids": sorted(old_documents)},
                )
            requested_document = next(iter(old_documents))
        if any(item.logical_vb_id != requested_document for item in old_versions):
            raise ValidationError(
                "old candidates do not belong to target_logical_vb_id",
                details={"target_logical_vb_id": requested_document},
            )
        if any(item.logical_vb_id != requested_document for item in new_versions):
            raise ValidationError(
                "new candidates do not belong to target_logical_vb_id",
                details={"target_logical_vb_id": requested_document},
            )

        references = self.parser.parse(
            amendment_text,
            target_logical_vb_id=requested_document,
        )
        return self.matcher.match(
            target_logical_vb_id=requested_document,
            old_versions=old_versions,
            new_versions=new_versions,
            references=references,
        )

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_temporal_law_service, require_admin
from app.config import BE2Config, get_config
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.amendment_preview_service import AmendmentPreviewService
from app.services.temporal_law_service import TemporalLawService


router = APIRouter(
    tags=["Admin Legal Amendments"],
    dependencies=[Depends(require_admin())],
)


class AmendmentPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    amendment_text: str = Field(min_length=5, max_length=50_000)
    old_provision_ids: list[str] = Field(min_length=1, max_length=100)
    new_provision_ids: list[str] = Field(min_length=1, max_length=100)
    target_logical_vb_id: str | None = Field(default=None, min_length=1)


def _require_amendment_preview(config: BE2Config) -> None:
    if not (config.legal_provision_v2_read and config.amendment_preview_v2):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Amendment preview API is disabled",
        )


@router.post("/legal/amendments/preview", summary="Preview amendment pairing without graph mutation")
async def preview_legal_amendment(
    request: AmendmentPreviewRequest,
    config: BE2Config = Depends(get_config),
    temporal_service: TemporalLawService = Depends(get_temporal_law_service),
) -> dict[str, Any]:
    _require_amendment_preview(config)
    service = AmendmentPreviewService(temporal_service)
    result = await service.preview(
        amendment_text=request.amendment_text,
        old_provision_ids=request.old_provision_ids,
        new_provision_ids=request.new_provision_ids,
        target_logical_vb_id=request.target_logical_vb_id,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        request_id=get_request_id(),
    )

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.api.deps import get_db_pool, get_neo4j_driver, require_admin, UserToken
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.social_facade import SocialAlertFacade

router = APIRouter(tags=["Admin Alerts"], dependencies=[Depends(require_admin())])


class AlertTriageRequest(BaseModel):
    action: str = Field(..., description="Hành động xử lý: investigate, create_suggest, resolve, dismiss")
    note: str | None = Field(default=None, description="Ghi chú nghiệp vụ/lý do xử lý")


@router.get("/alerts", summary="Danh sách tín hiệu có nguy cơ gây hiểu nhầm")
async def list_alerts(
    severity: str | None = None,
    status_filter: str | None = None,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    items = await facade.list_alerts(severity=severity, status=status_filter)
    return success_response(data={"items": items, "total": len(items)}, request_id=get_request_id())


@router.get("/alerts/{id}", summary="Chi tiết cảnh báo & các bài viết trong cụm (cluster)")
async def get_alert(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    item = await facade.get_alert_detail(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cảnh báo {id} không tồn tại")
    return success_response(data=item, request_id=get_request_id())


@router.patch("/alerts/{id}", summary="Phân loại & xử lý (triage) cảnh báo")
async def triage_alert(
    id: str,
    request: AlertTriageRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    alert = await facade.get_alert_detail(id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cảnh báo {id} không tồn tại")

    res = await facade.triage_alert(
        alert_id=id,
        action=request.action,
        note=request.note,
        user_id=user.user_id,
    )
    return success_response(data=res, request_id=get_request_id())

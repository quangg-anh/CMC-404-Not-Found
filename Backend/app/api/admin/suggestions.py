from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.api.deps import get_db_pool, get_neo4j_driver, require_admin, UserToken
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.suggest_service import SuggestService

router = APIRouter(tags=["Admin Suggestions"], dependencies=[Depends(require_admin())])


class GenerateSuggestRequest(BaseModel):
    tieu_de: str | None = Field(default=None, description="Têu đề đề xuất đính chính")
    noi_dung_dinh_chinh: str | None = Field(default=None, description="Nội dung đính chính")
    khoan_doi_chieu_id: str | None = Field(default=None, description="ID Khoản pháp lý làm căn cứ")


class UpdateSuggestRequest(BaseModel):
    tieu_de: str | None = None
    noi_dung_dinh_chinh: str | None = None
    khoan_doi_chieu_id: str | None = None
    status: str | None = Field(default=None, description="Trạng thái: draft, ready, exported")


@router.get("/suggestions", summary="Danh sách đề xuất đính chính (Suggestions)")
async def list_suggestions(
    status_filter: str | None = None,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    service = SuggestService(pool=pool, neo4j_driver=driver)
    items = await service.list_suggestions(status=status_filter)
    return success_response(data={"items": items, "total": len(items)}, request_id=get_request_id())


@router.post("/suggestions/generate", summary="Khởi tạo bản nháp Đề Xuất Đính Chính tự động")
async def generate_suggestion(
    request: GenerateSuggestRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    service = SuggestService(pool=pool, neo4j_driver=driver)
    data = await service.generate_suggestion(request.model_dump(), user_id=user.user_id)
    return success_response(data=data, request_id=get_request_id())


@router.get("/suggestions/{id}", summary="Chi tiết đề xuất đính chính")
async def get_suggestion(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    service = SuggestService(pool=pool, neo4j_driver=driver)
    item = await service.get_suggestion(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Suggestion {id} không tồn tại")
    return success_response(data=item, request_id=get_request_id())


@router.patch("/suggestions/{id}", summary="Cập nhật hoặc chuyển trạng thái Đề Xuất Đính Chính")
async def update_suggestion(
    id: str,
    request: UpdateSuggestRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    service = SuggestService(pool=pool, neo4j_driver=driver)
    try:
        item = await service.update_suggestion(id, request.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Suggestion {id} không tồn tại")
    return success_response(data=item, request_id=get_request_id())


@router.delete("/suggestions/{id}", summary="Xóa đề xuất đính chính")
async def delete_suggestion(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    service = SuggestService(pool=pool, neo4j_driver=driver)
    item = await service.delete_suggestion(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Suggestion {id} không tồn tại")
    return success_response(data={"id": id, "deleted": True}, request_id=get_request_id())

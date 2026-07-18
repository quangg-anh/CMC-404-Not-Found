from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.api.deps import get_db_pool, get_neo4j_driver, require_admin, require_roles, Role, UserToken
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.brief_service import BriefService
from app.services.phapluat_news_service import PhapLuatNewsService

router = APIRouter(tags=["Admin Briefs"], dependencies=[Depends(require_admin())])


class GenerateBriefRequest(BaseModel):
    tieu_de: str | None = Field(default=None, description="Têu đề bài tóm tắt")
    noi_dung: str | None = Field(default=None, description="Nội dung/Dàn ý tóm tắt")
    citations: list[dict[str, Any]] = Field(default_factory=list, description="Trích dẫn pháp lý")
    media_types: list[str] = Field(default_factory=lambda: ["article"], description="Định dạng: article, qa, infographic, video_script")


class UpdateBriefRequest(BaseModel):
    tieu_de: str | None = None
    noi_dung: str | None = None
    media_types: list[str] | None = None
    citations: list[dict[str, Any]] | None = None

class SyncNewsBriefsRequest(BaseModel):
    limit_per_topic: int = Field(default=5, ge=1, le=20)


@router.get("/briefs", summary="Danh sách bài tóm tắt (Content Briefs)")
async def list_briefs(
    status_filter: str | None = None,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    service = BriefService(pool=pool, neo4j_driver=driver)
    items = await service.list_briefs(status=status_filter)
    return success_response(data={"items": items, "total": len(items)}, request_id=get_request_id())


@router.post("/briefs/generate", summary="Khởi tạo bản nháp Bài Tóm Tắt tự động từ ngữ cảnh")
async def generate_brief(
    request: GenerateBriefRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    service = BriefService(pool=pool, neo4j_driver=driver)
    data = await service.generate_brief(request.model_dump(), user_id=user.user_id)
    return success_response(data=data, request_id=get_request_id())


@router.post("/briefs/sync-news", summary="Cập nhật bản tin pháp luật từ phapluat.gov.vn")
async def sync_news_briefs(
    request: SyncNewsBriefsRequest,
    pool: Any = Depends(get_db_pool),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    service = PhapLuatNewsService(pool=pool)
    data = await service.sync_briefs(user_id=user.user_id, limit_per_topic=request.limit_per_topic)
    return success_response(data=data, request_id=get_request_id())

@router.get("/briefs/{id}", summary="Chi tiết bài tóm tắt")
async def get_brief(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    service = BriefService(pool=pool, neo4j_driver=driver)
    item = await service.get_brief(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Brief {id} không tồn tại")
    return success_response(data=item, request_id=get_request_id())


@router.patch("/briefs/{id}", summary="Cập nhật bản nháp bài tóm tắt")
async def update_brief(
    id: str,
    request: UpdateBriefRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    service = BriefService(pool=pool, neo4j_driver=driver)
    item = await service.update_brief(id, request.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Brief {id} không tồn tại")
    return success_response(data=item, request_id=get_request_id())


@router.post("/briefs/{id}/publish", summary="Xuất bản Bài Tóm Tắt (Được bảo vệ bởi PublishGate)")
async def publish_brief(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
    user: UserToken = Depends(require_roles(Role.ADMIN_TRUYEN_THONG, Role.ADMIN_OPS)),
) -> dict[str, Any]:
    service = BriefService(pool=pool, neo4j_driver=driver)
    ok, data, errors = await service.publish_brief(id, actor=user)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Từ chối xuất bản bởi PublishGate", "errors": errors},
        )
    return success_response(data=data, request_id=get_request_id())


@router.post("/briefs/{id}/archive", summary="Lưu trữ/Ẩn bài tóm tắt")
async def archive_brief(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    service = BriefService(pool=pool, neo4j_driver=driver)
    item = await service.archive_brief(id, actor=user)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Brief {id} không tồn tại")
    return success_response(data=item, request_id=get_request_id())

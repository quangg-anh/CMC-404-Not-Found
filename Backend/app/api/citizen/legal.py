from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import get_db_pool, get_neo4j_driver
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.diff_facade import LegalDiffFacade

router = APIRouter(tags=["Citizen Legal"])


@router.get("/legal/van-ban", summary="Danh sách văn bản pháp luật công khai")
async def citizen_list_van_ban(
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    # Strictly enforce visibility=public for citizen
    items = await facade.list_van_ban(visibility="public")
    return success_response(data={"items": items, "total": len(items)}, request_id=get_request_id())


@router.get("/legal/van-ban/{id}", summary="Chi tiết cây văn bản pháp luật công khai")
async def citizen_get_van_ban(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    item = await facade.get_van_ban_detail(id)
    if not item or item.get("visibility") != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Văn bản không tồn tại hoặc chưa được công khai")
    return success_response(data=item, request_id=get_request_id())


@router.get("/legal/van-ban/{id}/files", summary="Danh sách file đính kèm văn bản công khai")
async def citizen_list_van_ban_files(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    doc = await facade.get_van_ban_detail(id)
    if not doc or doc.get("visibility") != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Văn bản không tồn tại hoặc chưa được công khai")
    files = await facade.list_files(id)
    return success_response(data={"files": files, "total": len(files)}, request_id=get_request_id())


@router.get("/legal/files/{file_id}", summary="Tải file điều luật công khai")
async def citizen_get_file_detail(
    file_id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    item = await facade.get_file_detail(file_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File không tồn tại")
    # Fail-closed visibility: trả file CHỈ khi bản thân file public VÀ văn bản cha cũng public.
    # (Dùng AND, không phải OR: một file internal thuộc văn bản public vẫn phải bị chặn.)
    van_ban_id = item.get("van_ban_id") or item.get("vb_id")
    parent = await facade.get_van_ban_detail(str(van_ban_id)) if van_ban_id else None
    file_public = item.get("visibility") == "public"
    parent_public = parent is None or parent.get("visibility") == "public"
    is_public = file_public and parent_public
    if not is_public:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File không công khai")
    return success_response(data=item, request_id=get_request_id())


@router.get("/legal/khoan/{id:path}", summary="Chi tiết Khoản công khai và nguyên văn")
async def citizen_get_khoan(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    item = await facade.get_khoan_detail(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khoản không tồn tại")
    # Verify visibility if parent doc or node has visibility field
    if item.get("visibility", "public") != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khoản không công khai")
    return success_response(data=item, request_id=get_request_id())

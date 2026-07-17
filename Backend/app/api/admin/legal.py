from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from app.api.deps import (
    get_db_pool,
    get_neo4j_driver,
    get_qdrant_client,
    get_embedder,
    get_minio,
    require_admin,
    UserToken,
)
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.diff_facade import LegalDiffFacade

# Max upload size (25 MB) — guards against accidental huge uploads on the sync path.
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024

router = APIRouter(tags=["Admin Legal"], dependencies=[Depends(require_admin())])


class IngestLegalRequest(BaseModel):
    so_hieu: str = Field(..., description="Số hiệu văn bản, ví dụ: 15/2020/NĐ-CP")
    ten: str | None = Field(default=None, description="Tên văn bản")
    url_or_content: str | None = Field(default=None, description="URL hoặc nội dung text văn bản")
    file_ids: list[str] = Field(default_factory=list, description="Danh sách ID file đính kèm đã upload")


class LegalDiffRequest(BaseModel):
    old_text: str = Field(..., description="Nội dung/Khoản văn bản cũ")
    new_text: str = Field(..., description="Nội dung/Khoản văn bản mới")
    method: str = Field(default="auto", description="Phương pháp diff: auto, exact, similarity")


@router.post("/legal/upload", summary="Tải file gốc (PDF/DOCX/TXT) lên MinIO để số hóa")
async def upload_legal_file(
    file: UploadFile = File(..., description="File văn bản gốc: PDF, DOCX hoặc TXT"),
    so_hieu: str = Form(..., description="Số hiệu văn bản để gắn file"),
    visibility: str = Form("internal", description="public | internal"),
    pool: Any = Depends(get_db_pool),
    minio: Any = Depends(get_minio),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    if minio is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Object storage (MinIO) chưa sẵn sàng; không thể lưu file.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File vượt quá giới hạn {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
        )
    facade = LegalDiffFacade(pool=pool, minio=minio)
    try:
        res = await facade.store_upload(
            filename=file.filename or "upload.bin",
            content_type=file.content_type,
            data=data,
            so_hieu=so_hieu,
            visibility=visibility,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return success_response(data=res, request_id=get_request_id())


@router.post("/ingest/legal", summary="Đẩy văn bản pháp luật vào pipeline xử lý")
async def ingest_legal(
    request: IngestLegalRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
    qdrant: Any = Depends(get_qdrant_client),
    embedder: Any = Depends(get_embedder),
    minio: Any = Depends(get_minio),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver, qdrant=qdrant, embedder=embedder, minio=minio)
    res = await facade.ingest_document(request.model_dump())
    return success_response(data=res, request_id=get_request_id())


@router.get("/legal/van-ban", summary="Danh sách văn bản pháp luật")
async def list_van_ban(
    visibility: str | None = None,
    trang_thai: str | None = None,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    items = await facade.list_van_ban(visibility=visibility, status=trang_thai)
    return success_response(data={"items": items, "total": len(items)}, request_id=get_request_id())


@router.get("/legal/van-ban/{id}", summary="Chi tiết cây Điều-Khoản-Điểm của văn bản")
async def get_van_ban(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    item = await facade.get_van_ban_detail(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Văn bản {id} không tồn tại")
    return success_response(data=item, request_id=get_request_id())


@router.get("/legal/van-ban/{id}/files", summary="Danh sách file đính kèm văn bản")
async def list_van_ban_files(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    files = await facade.list_files(id)
    return success_response(data={"files": files, "total": len(files)}, request_id=get_request_id())


@router.get("/legal/files/{file_id}", summary="Chi tiết & URL tải file gốc")
async def get_file_detail(
    file_id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    item = await facade.get_file_detail(file_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File {file_id} không tồn tại")
    return success_response(data=item, request_id=get_request_id())


@router.get("/legal/khoan/{id:path}", summary="Chi tiết Điều/Khoản & thực thể pháp lý")
async def get_khoan(
    id: str,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    item = await facade.get_khoan_detail(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Khoản {id} không tồn tại")
    return success_response(data=item, request_id=get_request_id())


@router.post("/legal/diff", summary="So sánh thay đổi giữa hai văn bản/Khoản")
async def compute_diff(
    request: LegalDiffRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver)
    diff_data = await facade.compute_diff(request.old_text, request.new_text, method=request.method)
    return success_response(data=diff_data, request_id=get_request_id())

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.pipelines.legal.pipeline import run_legal_ingest
from app.pipelines.legal.extractor import LegalExtractor

logger = logging.getLogger(__name__)

_JOB_STATUSES = {"queued", "running", "success", "error", "needs_review"}


async def _set_job_status(pool: Any, job_id: str, status: str, message: str | None = None) -> None:
    if not (pool and hasattr(pool, "acquire")):
        return
    db_status = status if status in _JOB_STATUSES else "error"
    err = message if db_status in {"error", "needs_review"} else None
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE jobs SET status = $1::job_status, error = $2, updated_at = now() WHERE id = $3::uuid",
                db_status,
                err,
                job_id,
            )
    except Exception:
        logger.exception("legal_ingest: failed to update job %s", job_id)


async def legal_ingest(ctx, job_id: str, payload: Dict[str, Any]):
    """Async worker: parse a legal document and upsert Điều/Khoản into Neo4j, then run NER.

    Shares the exact orchestration with the synchronous API path (``run_legal_ingest``).
    """
    driver = ctx.get("neo4j_driver")
    pool = ctx.get("db_pool")
    qdrant = ctx.get("qdrant")
    embedder = ctx.get("embedder")
    llm_router = ctx.get("llm_router")  # injected by worker_startup in arq_settings.py
    minio = ctx.get("minio")
    logger.info("Worker 'legal_ingest' processing job %s (so_hieu=%s)", job_id, payload.get("so_hieu"))

    await _set_job_status(pool, job_id, "running")
    try:
        result = await run_legal_ingest(
            driver,
            payload,
            qdrant=qdrant,
            embedder=embedder,
            llm_router=llm_router,
            pool=pool,
            minio=minio,
            config=ctx.get("config"),
        )
    except Exception as exc:  # noqa: BLE001
        await _set_job_status(pool, job_id, "error", str(exc))
        logger.exception("legal_ingest job %s failed", job_id)
        return {"status": "error", "job_id": job_id, "error": str(exc)}

    await _set_job_status(pool, job_id, result["status"], result.get("message"))
    result["job_id"] = job_id
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    return result


async def legal_parse(ctx, file_id: str):
    """Job Worker gọi Parser nếu được tách riêng thành queue độc lập."""
    logger.info("Worker 'legal_parse' đang chạy cho file: %s", file_id)
    # TODO: read file bytes from storage, call LegalParser, persist to Neo4j
    pass


async def legal_extract(ctx, khoan_id: str, khoan_text: str):
    """Job Worker gọi LegalExtractor (NER/RE) cho một Khoản cụ thể.

    Được enqueue sau khi legal_ingest hoàn thành nếu cần xử lý NER riêng lẻ.
    """
    llm_router = ctx.get("llm_router")
    logger.info("Worker 'legal_extract' trích xuất thực thể cho khoản: %s", khoan_id)
    if llm_router is None:
        logger.warning("legal_extract: llm_router not in worker context — skipping NER for %s", khoan_id)
        return {"status": "skipped", "khoan_id": khoan_id, "reason": "no_llm_router"}

    extractor = LegalExtractor(llm_router=llm_router)
    result = await extractor.extract_entities_from_khoan(khoan_id, khoan_text)
    logger.info(
        "legal_extract: done for %s — chu_the=%d nghia_vu=%d skip=%s",
        khoan_id,
        len(result.get("chu_the", [])),
        len(result.get("nghia_vu", [])),
        result.get("_skip_reason", ""),
    )
    return {"status": "success", "khoan_id": khoan_id, "entities": result}


async def legal_diff(ctx, old_vb_id: str, new_vb_id: str):
    """Job Worker gọi VersionDiff.
    Thường được trigger thủ công bởi Admin qua `/admin/legal/diff`.
    """
    logger.info("Worker 'legal_diff' đang so sánh 2 văn bản: %s và %s", old_vb_id, new_vb_id)
    # TODO: fetch texts from Neo4j, call VersionDiff.diff()
    pass

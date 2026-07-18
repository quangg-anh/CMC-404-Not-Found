"""Admin review queue: legal ingest jobs + Neo4j nodes flagged needs_review.

Legal digitization marks failures as ``jobs.status = 'needs_review'`` in Postgres — that is the
primary source of "văn bản cần duyệt". Neo4j ``n.needs_review = true`` covers social posts / NER
items. Earlier this endpoint only queried Neo4j, so the queue looked empty despite dozens of
legal jobs waiting for human review.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import UserToken, get_db_pool, get_neo4j_driver, require_admin
from app.core.envelope import success_response
from app.core.logging import get_request_id

router = APIRouter(tags=["Admin Review"], dependencies=[Depends(require_admin())])


class ReviewActionRequest(BaseModel):
    action: str = Field(..., description="Hành động: approve, reject, override")
    override_data: dict[str, Any] | None = Field(default=None, description="Dữ liệu ghi đè nếu action là override")
    note: str | None = Field(default=None, description="Ghi chú nghiệp vụ")


def _parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return {}
    return {}


async def _jobs_needing_review(pool: Any, type_filter: str | None) -> list[dict[str, Any]]:
    """Pull legal/social ingest jobs stuck in needs_review from Postgres."""
    if not (pool and hasattr(pool, "acquire")):
        return []
    items: list[dict[str, Any]] = []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id::text AS id, type, status::text AS status, stage,
                       payload_json, error, created_at, updated_at
                FROM jobs
                WHERE status = 'needs_review'::job_status
                ORDER BY created_at DESC
                LIMIT 200
                """
            )
        for row in rows:
            payload = _parse_payload(row["payload_json"])
            job_type = str(row["type"] or "")
            # Map job type → review item type for the UI.
            if "legal" in job_type or job_type in {"parse", "extract", "diff"}:
                item_type = "legal_ingest"
            elif "social" in job_type:
                item_type = "social_ingest"
            elif "brief" in job_type:
                item_type = "brief"
            else:
                item_type = "job"

            if type_filter and item_type != type_filter and type_filter != "job":
                # Also allow filtering by raw job type alias from the UI.
                if type_filter not in {item_type, job_type, "legal_khoan"}:
                    continue
                if type_filter == "legal_khoan" and item_type != "legal_ingest":
                    continue

            so_hieu = str(payload.get("so_hieu") or payload.get("ten") or "").strip()
            reason = str(row["error"] or payload.get("message") or "Job cần cán bộ rà soát").strip()
            content_bits = [b for b in [so_hieu, reason] if b]
            items.append(
                {
                    "id": f"job:{row['id']}",
                    "job_id": row["id"],
                    "type": item_type,
                    "source": job_type,
                    "so_hieu": so_hieu or None,
                    "content": " — ".join(content_bits) if content_bits else "(Không có mô tả)",
                    "reason": reason[:300],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                    "payload": {
                        "so_hieu": payload.get("so_hieu"),
                        "ten": payload.get("ten"),
                        "file_ids": payload.get("file_ids"),
                        "vb_id": payload.get("vb_id"),
                    },
                }
            )
    except Exception:
        return items
    return items


async def _neo4j_needing_review(driver: Any, type_filter: str | None) -> list[dict[str, Any]]:
    """Pull graph nodes explicitly flagged needs_review (social posts, NER entities, …)."""
    if not (driver and hasattr(driver, "session")):
        return []
    items: list[dict[str, Any]] = []
    try:
        query = """
        MATCH (n)
        WHERE n.needs_review = true
        RETURN id(n) AS nid, labels(n) AS labels, n
        LIMIT 100
        """
        async with driver.session() as session:
            res = await session.run(query)
            async for record in res:
                n = record["n"]
                lbls = list(record["labels"] or [])
                if "BaiDang" in lbls:
                    item_type = "social_post"
                elif "Khoan" in lbls or "Dieu" in lbls or "VanBanPhapLuat" in lbls:
                    item_type = "legal_khoan"
                else:
                    item_type = "entity"
                if type_filter and item_type != type_filter:
                    continue
                node_id = str(
                    n.get("bai_dang_id")
                    or n.get("khoan_id")
                    or n.get("dieu_id")
                    or n.get("vb_id")
                    or n.get("so_hieu")
                    or record["nid"]
                )
                items.append(
                    {
                        "id": f"neo4j:{node_id}",
                        "type": item_type,
                        "source": ",".join(lbls),
                        "so_hieu": n.get("so_hieu"),
                        "content": str(
                            n.get("noi_dung") or n.get("ten") or n.get("tieu_de") or node_id
                        )[:500],
                        "reason": str(
                            n.get("review_reason")
                            or "Độ tin cậy thấp khi bóc tách BE1/BE2"
                        ),
                        "created_at": str(n.get("ngay_dang") or n.get("created_at") or ""),
                    }
                )
    except Exception:
        return items
    return items


@router.get("/review", summary="Danh sách hàng đợi cần duyệt (jobs + Neo4j needs_review)")
async def list_review_queue(
    type: str | None = None,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    job_items = await _jobs_needing_review(pool, type)
    neo_items = await _neo4j_needing_review(driver, type)
    items = job_items + neo_items
    return success_response(
        data={"items": items, "total": len(items)},
        request_id=get_request_id(),
    )


@router.patch("/review/{item_id}", summary="Phê duyệt hoặc từ chối phần tử trong hàng đợi review")
async def process_review_item(
    item_id: str,
    request: ReviewActionRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    action = (request.action or "").strip().lower()
    if action not in {"approve", "reject", "override"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="action must be approve|reject|override")

    processed = False

    # Job-backed review items (legal ingest, …)
    if item_id.startswith("job:") or _looks_like_uuid(item_id):
        job_id = item_id.removeprefix("job:")
        if pool and hasattr(pool, "acquire"):
            try:
                new_status = "success" if action in {"approve", "override"} else "error"
                note = request.note or (
                    f"Reviewed ({action}) by {user.user_id}"
                )
                async with pool.acquire() as conn:
                    result = await conn.execute(
                        """
                        UPDATE jobs
                        SET status = $1::job_status,
                            error = CASE WHEN $1::text = 'success' THEN NULL ELSE COALESCE(error, $2) END,
                            stage = 'reviewed',
                            updated_at = now()
                        WHERE id = $3::uuid AND status = 'needs_review'::job_status
                        """,
                        new_status,
                        note,
                        job_id,
                    )
                processed = False
                if isinstance(result, str):
                    try:
                        processed = int(result.split()[-1]) > 0
                    except (ValueError, IndexError):
                        processed = result.endswith("1")
                else:
                    processed = bool(result)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"job update failed: {exc}") from exc

    # Neo4j-backed review items
    if item_id.startswith("neo4j:") or not processed:
        neo_id = item_id.removeprefix("neo4j:")
        if driver and hasattr(driver, "session"):
            try:
                # approve → clear flag; reject → clear flag + mark rejected
                query = """
                MATCH (n)
                WHERE n.bai_dang_id = $id OR n.khoan_id = $id OR n.dieu_id = $id
                   OR n.vb_id = $id OR n.so_hieu = $id OR toString(id(n)) = $id
                SET n.needs_review = false,
                    n.reviewed_by = $user,
                    n.review_action = $action,
                    n.review_note = $note
                RETURN count(n) AS c
                """
                async with driver.session() as session:
                    res = await session.run(
                        query,
                        id=neo_id,
                        user=user.user_id,
                        action=action,
                        note=request.note or "",
                    )
                    rec = await res.single()
                    if rec and int(rec.get("c") or 0) > 0:
                        processed = True
            except Exception:
                pass

    if not processed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Review item not found: {item_id}")

    return success_response(
        data={
            "id": item_id,
            "action": action,
            "status": "processed",
            "reviewed_by": user.user_id,
            "note": request.note,
        },
        request_id=get_request_id(),
    )


def _looks_like_uuid(value: str) -> bool:
    parts = value.split("-")
    return len(parts) == 5 and all(parts)


__all__ = ["router"]

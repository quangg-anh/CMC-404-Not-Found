from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_db_pool, require_admin
from app.core.envelope import success_response
from app.core.logging import get_request_id

router = APIRouter(tags=["Admin Jobs"], dependencies=[Depends(require_admin())])


def _parse_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return raw
    return raw


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@router.get("/jobs", summary="Danh sách jobs & tổng quan sức khỏe pipeline")
async def list_jobs(
    type: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    pool: Any = Depends(get_db_pool),
) -> dict[str, Any]:
    """Return real jobs from Postgres only — empty list after purge is correct."""
    items: list[dict[str, Any]] = []
    running = queued = failed = needs_review = 0

    if pool and hasattr(pool, "acquire"):
        try:
            async with pool.acquire() as conn:
                # Full-table summary (not limited to the page of items).
                for row in await conn.fetch(
                    """
                    SELECT status::text AS status, COUNT(*)::int AS cnt
                    FROM jobs
                    GROUP BY status
                    """
                ):
                    st = str(row["status"] or "").lower()
                    cnt = int(row["cnt"] or 0)
                    if st == "running":
                        running = cnt
                    elif st == "queued":
                        queued = cnt
                    elif st in {"error", "failed"}:
                        failed += cnt
                    elif st == "needs_review":
                        needs_review = cnt

                clauses: list[str] = []
                args: list[Any] = []
                if type:
                    args.append(type)
                    clauses.append(f"type = ${len(args)}")
                if status_filter:
                    args.append(status_filter)
                    clauses.append(f"status::text = ${len(args)}")
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                args.append(max(1, min(limit, 500)))
                rows = await conn.fetch(
                    f"""
                    SELECT id, type, status::text AS status, payload_json, error, created_at
                    FROM jobs
                    {where}
                    ORDER BY created_at DESC
                    LIMIT ${len(args)}
                    """,
                    *args,
                )
                for r in rows:
                    st = str(r["status"] or "")
                    items.append(
                        {
                            "job_id": str(r["id"]),
                            "type": r["type"],
                            "status": st,
                            "payload": _parse_json(r["payload_json"]) or {},
                            "error": _parse_json(r["error"]),
                            "created_at": _iso(r["created_at"]),
                            "needs_review": st == "needs_review",
                        }
                    )
        except Exception:
            # Keep empty list — never invent mock history after purge.
            items = []

    return success_response(
        data={
            "items": items,
            "total": len(items),
            "summary": {
                "total_running": running,
                "total_queued": queued,
                "total_failed": failed,
                "total_needs_review": needs_review,
                "health": "healthy" if failed == 0 else "degraded",
            },
        },
        request_id=get_request_id(),
    )


@router.get("/jobs/{id}", summary="Chi tiết & tiến trình (stepper) của một job")
async def get_job_detail(
    id: str,
    pool: Any = Depends(get_db_pool),
) -> dict[str, Any]:
    if not (pool and hasattr(pool, "acquire")):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, type, status::text AS status, stage, payload_json, error, created_at, updated_at
                FROM jobs WHERE id::text = $1
                """,
                id,
            )
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {id} không tồn tại")

            events = await conn.fetch(
                """
                SELECT stage, status::text AS status, message, at
                FROM job_events
                WHERE job_id::text = $1
                ORDER BY at ASC
                """,
                id,
            )
            stages = [
                {
                    "stage": e["stage"],
                    "status": e["status"],
                    "message": e["message"],
                    "completed_at": _iso(e["at"]),
                }
                for e in events
            ]
            # If no event log yet, expose current stage from the job row.
            if not stages and row.get("stage"):
                stages = [
                    {
                        "stage": row["stage"],
                        "status": row["status"],
                        "message": None,
                        "completed_at": _iso(row.get("updated_at") or row.get("created_at")),
                    }
                ]

            return success_response(
                data={
                    "job_id": str(row["id"]),
                    "type": row["type"],
                    "status": row["status"],
                    "stage": row.get("stage"),
                    "payload": _parse_json(row["payload_json"]) or {},
                    "error": _parse_json(row["error"]),
                    "created_at": _iso(row["created_at"]),
                    "updated_at": _iso(row.get("updated_at")),
                    "stages": stages,
                },
                request_id=get_request_id(),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không đọc được job: {exc}",
        ) from exc

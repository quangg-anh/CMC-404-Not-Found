from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Iterable

from app.adapters.neo4j_legal_v2 import prepare_legal_provision_rows


LEGAL_PROVISION_COLLECTION = "legal_provision"
_PROVISION_POINT_NAMESPACE = uuid.UUID("2b5f2a91-20eb-4c68-bd7d-3e7fa8b4a126")

_LEAF_QUERY = """
/* legal_v2_leaf_inventory */
MATCH (p:LegalProvision)
WHERE NOT EXISTS {
    MATCH (p)-[:CO_KHOAN|CO_DIEM]->(:LegalProvision)
}
  AND ($document_id IS NULL
       OR p.logical_vb_id = $document_id
       OR p.source_vb_id = $document_id)
  AND ($resume_from IS NULL OR p.provision_id > $resume_from)
RETURN p.provision_id AS provision_id,
       p.lineage_id AS lineage_id,
       p.level AS level,
       p.logical_vb_id AS logical_vb_id,
       p.source_vb_id AS source_vb_id,
       p.effective_from AS effective_from,
       p.effective_to AS effective_to,
       coalesce(p.visibility, 'public') AS visibility,
       coalesce(p.review_status, 'approved') AS review_status,
       p.text_checksum AS text_checksum,
       coalesce(p.noi_dung, p.tieu_de, '') AS text
ORDER BY p.provision_id
"""


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())[:10]
    return str(value)[:10]


def _qdrant_datetime(value: Any) -> str | None:
    date_value = _iso_date(value)
    return f"{date_value}T00:00:00Z" if date_value else None


def deterministic_provision_point_id(provision_id: str) -> str:
    """Return the stable Qdrant UUID for one immutable provision version."""
    if not provision_id or not provision_id.strip():
        raise ValueError("provision_id is required")
    return str(uuid.uuid5(_PROVISION_POINT_NAMESPACE, provision_id.strip()))


def select_deepest_leaf_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select Point, otherwise Clause, otherwise Article from a v2 document tree."""
    materialized = [dict(row) for row in rows]
    parent_lineages = {
        str(row["parent_lineage_id"])
        for row in materialized
        if row.get("parent_lineage_id")
    }
    leaves = [
        row
        for row in materialized
        if row.get("lineage_id") not in parent_lineages
        and row.get("provision_id")
        and str(row.get("text") or "").strip()
    ]
    return sorted(leaves, key=lambda row: str(row["provision_id"]))


def legal_provision_payload(
    row: dict[str, Any],
    *,
    include_debug_preview: bool = False,
) -> dict[str, Any]:
    """Build an ID-only retrieval payload; Neo4j remains the citation source."""
    required = (
        "provision_id",
        "lineage_id",
        "level",
        "logical_vb_id",
        "source_vb_id",
        "effective_from",
        "text_checksum",
    )
    missing = [name for name in required if row.get(name) in (None, "")]
    if missing:
        raise ValueError(f"missing legal_provision payload fields: {', '.join(missing)}")

    payload: dict[str, Any] = {
        "provision_id": str(row["provision_id"]),
        "lineage_id": str(row["lineage_id"]),
        "level": str(row["level"]),
        "logical_vb_id": str(row["logical_vb_id"]),
        "source_vb_id": str(row["source_vb_id"]),
        "effective_from": _qdrant_datetime(row["effective_from"]),
        "effective_to": _qdrant_datetime(row.get("effective_to")),
        "visibility": str(row.get("visibility") or "public"),
        "review_status": str(row.get("review_status") or "approved"),
        "text_checksum": str(row["text_checksum"]),
    }
    if include_debug_preview:
        payload["text_preview"] = str(row.get("text") or "")[:200]
    return payload


def build_legal_provision_points(
    rows: list[dict[str, Any]],
    vectors: list[list[float]],
    *,
    include_debug_preview: bool = False,
) -> list[dict[str, Any]]:
    if len(rows) != len(vectors):
        raise ValueError("embedding count does not match legal provision count")
    return [
        {
            "id": deterministic_provision_point_id(str(row["provision_id"])),
            "vector": vector,
            "payload": legal_provision_payload(
                row,
                include_debug_preview=include_debug_preview,
            ),
        }
        for row, vector in zip(rows, vectors)
    ]


async def index_document_legal_provisions(
    qdrant: Any,
    embedder: Any,
    doc: dict[str, Any],
    *,
    include_debug_preview: bool = False,
) -> int:
    """Dual-index deepest immutable provisions for one successfully written v2 document."""
    if not (qdrant and embedder):
        return 0
    rows = select_deepest_leaf_rows(prepare_legal_provision_rows(doc))
    if not rows:
        return 0
    vectors = await embedder.embed_texts([str(row["text"]) for row in rows])
    points = build_legal_provision_points(
        rows,
        vectors,
        include_debug_preview=include_debug_preview,
    )
    await qdrant.upsert(LEGAL_PROVISION_COLLECTION, points)
    return len(points)


async def load_leaf_provisions_from_neo4j(
    driver: Any,
    *,
    document_id: str | None = None,
    resume_from: str | None = None,
) -> list[dict[str, Any]]:
    if not (driver and hasattr(driver, "session")):
        raise ValueError("neo4j_unavailable")
    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        result = await session.run(
            _LEAF_QUERY,
            document_id=document_id,
            resume_from=resume_from,
        )
        async for record in result:
            data = record.data() if callable(getattr(record, "data", None)) else dict(record)
            data["effective_from"] = _iso_date(data.get("effective_from"))
            data["effective_to"] = _iso_date(data.get("effective_to"))
            rows.append(data)
    return rows


async def reindex_legal_provisions_from_neo4j(
    driver: Any,
    qdrant: Any,
    embedder: Any,
    *,
    document_id: str | None = None,
    resume_from: str | None = None,
    batch_size: int = 32,
    skip_existing: bool = True,
    include_debug_preview: bool = False,
) -> dict[str, Any]:
    """Resumable Neo4j -> Qdrant v2 backfill with stable, idempotent point IDs."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if not (qdrant and embedder):
        return {
            "status": "error",
            "message": "qdrant_or_embedder_unavailable",
            "indexed": 0,
            "checkpoint": resume_from,
        }

    rows = await load_leaf_provisions_from_neo4j(
        driver,
        document_id=document_id,
        resume_from=resume_from,
    )
    total = len(rows)
    usable = [
        row
        for row in rows
        if row.get("provision_id")
        and str(row.get("text") or "").strip()
        and row.get("text_checksum")
        and row.get("effective_from")
    ]
    skipped_invalid = total - len(usable)
    skipped_existing = 0
    checksum_mismatches = 0
    if skip_existing and hasattr(qdrant, "list_payload_records"):
        records = await qdrant.list_payload_records(
            LEGAL_PROVISION_COLLECTION,
            ["provision_id", "text_checksum"],
        )
        existing_checksums = {
            str(record["provision_id"]): str(record.get("text_checksum") or "")
            for record in records
            if record.get("provision_id")
        }
        checksum_mismatches = sum(
            1
            for row in usable
            if str(row["provision_id"]) in existing_checksums
            and existing_checksums[str(row["provision_id"])]
            != str(row["text_checksum"])
        )
        before = len(usable)
        usable = [
            row
            for row in usable
            if existing_checksums.get(str(row["provision_id"]))
            != str(row["text_checksum"])
        ]
        skipped_existing = before - len(usable)
    elif skip_existing and hasattr(qdrant, "list_payload_values"):
        existing = await qdrant.list_payload_values(
            LEGAL_PROVISION_COLLECTION,
            "provision_id",
        )
        before = len(usable)
        usable = [row for row in usable if str(row["provision_id"]) not in existing]
        skipped_existing = before - len(usable)
    indexed = 0
    checkpoint = resume_from
    try:
        for start in range(0, len(usable), batch_size):
            batch = usable[start : start + batch_size]
            vectors = await embedder.embed_texts([str(row["text"]).strip() for row in batch])
            await qdrant.upsert(
                LEGAL_PROVISION_COLLECTION,
                build_legal_provision_points(
                    batch,
                    vectors,
                    include_debug_preview=include_debug_preview,
                ),
            )
            indexed += len(batch)
            checkpoint = str(batch[-1]["provision_id"])
    except Exception as exc:  # noqa: BLE001 - return checkpoint for safe resume
        return {
            "status": "partial" if indexed else "error",
            "message": str(exc),
            "document_id": document_id,
            "total": total,
            "usable": total - skipped_invalid,
            "skipped_invalid": skipped_invalid,
            "skipped_existing": skipped_existing,
            "checksum_mismatches": checksum_mismatches,
            "indexed": indexed,
            "checkpoint": checkpoint,
        }

    return {
        "status": "success",
        "document_id": document_id,
        "total": total,
        "usable": total - skipped_invalid,
        "skipped_invalid": skipped_invalid,
        "skipped_existing": skipped_existing,
        "checksum_mismatches": checksum_mismatches,
        "indexed": indexed,
        "checkpoint": checkpoint,
    }

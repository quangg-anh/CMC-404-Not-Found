from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


_INVENTORY_QUERY = """
/* legal_v2_migration_inventory */
MATCH (v:VanBanPhapLuat)
WHERE $document_id IS NULL
   OR v.vb_id = $document_id
   OR v.so_hieu = $document_id
OPTIONAL MATCH (v)-[:CO_DIEU]->(d:Dieu)
OPTIONAL MATCH (d)-[:CO_KHOAN]->(k:Khoan)
OPTIONAL MATCH (k)-[:CO_DIEM]->(p:Diem)
RETURN v.vb_id AS vb_id,
       v.so_hieu AS so_hieu,
       v.ngay_hieu_luc AS ngay_hieu_luc,
       v.ngay_ban_hanh AS ngay_ban_hanh,
       v.source_checksum AS source_checksum,
       v.source_filename AS source_filename,
       d.dieu_id AS dieu_id,
       d.provision_id AS dieu_provision_id,
       coalesce(d.noi_dung, d.tieu_de, '') AS dieu_text,
       k.khoan_id AS khoan_id,
       k.provision_id AS khoan_provision_id,
       k.noi_dung AS khoan_text,
       p.diem_id AS diem_id,
       p.provision_id AS diem_provision_id,
       p.noi_dung AS diem_text
ORDER BY vb_id, dieu_id, khoan_id, diem_id
"""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _node_map(
    rows: list[dict[str, Any]],
    *,
    id_field: str,
    provision_field: str,
    text_field: str,
) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for row in rows:
        node_id = _text(row.get(id_field))
        if not node_id:
            continue
        nodes.setdefault(
            node_id,
            {
                "id": node_id,
                "provision_id": _text(row.get(provision_field)) or None,
                "text": _text(row.get(text_field)),
            },
        )
    return nodes


def build_migration_inventory(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Classify legacy documents without mutating Neo4j or guessing missing Points."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        key = _text(row.get("vb_id")) or _text(row.get("so_hieu"))
        if key:
            grouped[key].append(row)

    documents: list[dict[str, Any]] = []
    totals = {
        "documents": 0,
        "articles": 0,
        "clauses": 0,
        "points": 0,
        "v2_nodes": 0,
        "already_v2": 0,
        "eligible_dry_run_upgrade": 0,
        "requires_reingest": 0,
        "requires_source_review": 0,
    }

    for key in sorted(grouped):
        doc_rows = grouped[key]
        first = doc_rows[0]
        articles = _node_map(doc_rows, id_field="dieu_id", provision_field="dieu_provision_id", text_field="dieu_text")
        clauses = _node_map(doc_rows, id_field="khoan_id", provision_field="khoan_provision_id", text_field="khoan_text")
        points = _node_map(doc_rows, id_field="diem_id", provision_field="diem_provision_id", text_field="diem_text")
        clause_point_ids: dict[str, set[str]] = {
            clause_id: set() for clause_id in clauses
        }
        for row in doc_rows:
            clause_id = _text(row.get("khoan_id"))
            point_id = _text(row.get("diem_id"))
            if clause_id and point_id:
                clause_point_ids.setdefault(clause_id, set()).add(point_id)
        clauses_without_points = sorted(
            clause_id
            for clause_id, point_ids in clause_point_ids.items()
            if not point_ids
        )
        all_nodes = [*articles.values(), *clauses.values(), *points.values()]
        v2_nodes = sum(1 for node in all_nodes if node["provision_id"])
        missing_text = [node["id"] for node in all_nodes if not node["text"]]
        has_effective_date = bool(_text(first.get("ngay_hieu_luc")) or _text(first.get("ngay_ban_hanh")))
        has_checksum = bool(_text(first.get("source_checksum")))
        has_raw_reference = bool(_text(first.get("source_filename")))
        point_coverage_unverified = bool(clauses_without_points)

        reasons: list[str] = []
        if not articles:
            reasons.append("no_articles")
        if not has_effective_date:
            reasons.append("missing_effective_date")
        if missing_text:
            reasons.append("missing_canonical_text")
        if not has_checksum:
            reasons.append("missing_source_checksum")
        if point_coverage_unverified:
            reasons.append("point_coverage_unverified")
        if point_coverage_unverified and not has_raw_reference:
            reasons.append("raw_source_required_to_verify_points")

        if not articles or not has_effective_date or missing_text:
            status = "requires_reingest"
        elif all_nodes and v2_nodes == len(all_nodes):
            status = "already_v2"
        elif point_coverage_unverified and not has_raw_reference:
            status = "requires_reingest"
        elif has_checksum and has_raw_reference:
            status = "eligible_dry_run_upgrade"
        else:
            status = "requires_source_review"
        counts = {"articles": len(articles), "clauses": len(clauses), "points": len(points), "v2_nodes": v2_nodes}
        documents.append(
            {
                "vb_id": _text(first.get("vb_id")) or key,
                "so_hieu": _text(first.get("so_hieu")) or None,
                "status": status,
                "counts": counts,
                "has_effective_date": has_effective_date,
                "has_source_checksum": has_checksum,
                "has_raw_source_reference": has_raw_reference,
                "point_coverage_unverified": point_coverage_unverified,
                "clauses_without_points": clauses_without_points,
                "missing_text_node_ids": missing_text,
                "reasons": reasons,
            }
        )
        totals["documents"] += 1
        totals["articles"] += len(articles)
        totals["clauses"] += len(clauses)
        totals["points"] += len(points)
        totals["v2_nodes"] += v2_nodes
        totals[status] += 1

    return {"mode": "dry_run_inventory", "mutated": False, "totals": totals, "documents": documents}


async def load_migration_inventory_rows(driver: Any, *, document_id: str | None = None) -> list[dict[str, Any]]:
    if not (driver and hasattr(driver, "session")):
        raise ValueError("neo4j_unavailable")
    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        result = await session.run(_INVENTORY_QUERY, document_id=document_id)
        async for record in result:
            rows.append(record.data() if callable(getattr(record, "data", None)) else dict(record))
    return rows


async def inspect_temporal_v2_migration(driver: Any, *, document_id: str | None = None) -> dict[str, Any]:
    rows = await load_migration_inventory_rows(driver, document_id=document_id)
    report = build_migration_inventory(rows)
    report["document_filter"] = document_id
    return report

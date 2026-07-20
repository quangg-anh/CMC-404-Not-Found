from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from app.domain.legal_provision import (
    ProvisionLevel,
    build_provision_version,
    canonicalize_legal_text,
)
from app.domain.legal_write import (
    LegalWriteConflict,
    LegalWriteCounts,
    LegalWriteReport,
    LegalWriteStatus,
)


_LEVEL_NAMES = tuple(level.value for level in ProvisionLevel)
_LEVEL_META = {
    "dieu": {
        "label": "Dieu",
        "legacy_key": "dieu_id",
        "legacy_text": "tieu_de",
        "marker": "dieu",
    },
    "khoan": {
        "label": "Khoan",
        "legacy_key": "khoan_id",
        "legacy_text": "noi_dung",
        "marker": "khoan",
    },
    "diem": {
        "label": "Diem",
        "legacy_key": "diem_id",
        "legacy_text": "noi_dung",
        "marker": "diem",
    },
}

_DOCUMENT_QUERY = """
/* legal_v2_write_document */
MERGE (v:VanBanPhapLuat {vb_id: $vb_id})
SET v.so_hieu = $so_hieu, v.ten = $ten, v.loai = $loai,
    v.ngay_ban_hanh = $ngay_ban_hanh, v.ngay_hieu_luc = $ngay_hieu_luc,
    v.trang_thai = $trang_thai, v.visibility = $visibility,
    v.co_quan_ban_hanh = $co_quan_ban_hanh,
    v.source_filename = $source_filename,
    v.source_checksum = $source_checksum
"""

_WRITE_QUERIES = {
    "dieu": """
/* legal_v2_write_dieu */
UNWIND $rows AS row
MATCH (v:VanBanPhapLuat {vb_id: $vb_id})
MERGE (p:Dieu {dieu_id: row.compatibility_id})
WITH v, p, row
WHERE p.provision_id IS NULL OR (
    p.provision_id = row.provision_id
    AND p.text_checksum = row.text_checksum
    AND p.lineage_id = row.lineage_id
    AND p.level = row.level
    AND p.version_no = row.version_no
    AND p.source_vb_id = row.source_vb_id
    AND (
        (p.source_checksum IS NULL AND row.source_checksum IS NULL)
        OR p.source_checksum = row.source_checksum
    )
    AND p.effective_from = date(row.effective_from)
    AND (
        (p.effective_to IS NULL AND row.effective_to IS NULL)
        OR p.effective_to = date(row.effective_to)
    )
)
SET p:LegalProvision,
    p.provision_id = row.provision_id,
    p.lineage_id = row.lineage_id,
    p.parent_lineage_id = null,
    p.level = row.level,
    p.version_no = row.version_no,
    p.so = row.article,
    p.so_dieu = row.article,
    p.tieu_de = row.title,
    p.noi_dung = row.text,
    p.effective_from = date(row.effective_from),
    p.effective_to = CASE WHEN row.effective_to IS NULL THEN null ELSE date(row.effective_to) END,
    p.text_checksum = row.text_checksum,
    p.source_checksum = row.source_checksum,
    p.source_vb_id = row.source_vb_id,
    p.logical_vb_id = row.logical_vb_id,
    p.van_ban_id = row.source_vb_id,
    p.visibility = coalesce(p.visibility, row.visibility),
    p.recorded_at = coalesce(p.recorded_at, datetime(row.recorded_at)),
    p.review_status = coalesce(p.review_status, row.review_status)
MERGE (v)-[:CO_DIEU]->(p)
RETURN count(p) AS written_count
""",
    "khoan": """
/* legal_v2_write_khoan */
UNWIND $rows AS row
MATCH (parent:LegalProvision:Dieu {provision_id: row.parent_provision_id})
MERGE (p:Khoan {khoan_id: row.compatibility_id})
WITH parent, p, row
WHERE p.provision_id IS NULL OR (
    p.provision_id = row.provision_id
    AND p.text_checksum = row.text_checksum
    AND p.lineage_id = row.lineage_id
    AND p.level = row.level
    AND p.version_no = row.version_no
    AND p.source_vb_id = row.source_vb_id
    AND (
        (p.source_checksum IS NULL AND row.source_checksum IS NULL)
        OR p.source_checksum = row.source_checksum
    )
    AND p.effective_from = date(row.effective_from)
    AND (
        (p.effective_to IS NULL AND row.effective_to IS NULL)
        OR p.effective_to = date(row.effective_to)
    )
)
SET p:LegalProvision,
    p.provision_id = row.provision_id,
    p.lineage_id = row.lineage_id,
    p.parent_lineage_id = row.parent_lineage_id,
    p.level = row.level,
    p.version_no = row.version_no,
    p.so = row.clause,
    p.so_khoan = row.clause,
    p.noi_dung = row.text,
    p.effective_from = date(row.effective_from),
    p.effective_to = CASE WHEN row.effective_to IS NULL THEN null ELSE date(row.effective_to) END,
    p.text_checksum = row.text_checksum,
    p.source_checksum = row.source_checksum,
    p.source_vb_id = row.source_vb_id,
    p.logical_vb_id = row.logical_vb_id,
    p.van_ban_id = row.source_vb_id,
    p.dieu_id = row.parent_compatibility_id,
    p.dieu_so = row.article,
    p.visibility = coalesce(p.visibility, row.visibility),
    p.recorded_at = coalesce(p.recorded_at, datetime(row.recorded_at)),
    p.review_status = coalesce(p.review_status, row.review_status)
MERGE (parent)-[:CO_KHOAN]->(p)
RETURN count(p) AS written_count
""",
    "diem": """
/* legal_v2_write_diem */
UNWIND $rows AS row
MATCH (parent:LegalProvision:Khoan {provision_id: row.parent_provision_id})
MERGE (p:Diem {diem_id: row.compatibility_id})
WITH parent, p, row
WHERE p.provision_id IS NULL OR (
    p.provision_id = row.provision_id
    AND p.text_checksum = row.text_checksum
    AND p.lineage_id = row.lineage_id
    AND p.level = row.level
    AND p.version_no = row.version_no
    AND p.source_vb_id = row.source_vb_id
    AND (
        (p.source_checksum IS NULL AND row.source_checksum IS NULL)
        OR p.source_checksum = row.source_checksum
    )
    AND p.effective_from = date(row.effective_from)
    AND (
        (p.effective_to IS NULL AND row.effective_to IS NULL)
        OR p.effective_to = date(row.effective_to)
    )
)
SET p:LegalProvision,
    p.provision_id = row.provision_id,
    p.lineage_id = row.lineage_id,
    p.parent_lineage_id = row.parent_lineage_id,
    p.level = row.level,
    p.version_no = row.version_no,
    p.ky_hieu = row.point,
    p.noi_dung = row.text,
    p.effective_from = date(row.effective_from),
    p.effective_to = CASE WHEN row.effective_to IS NULL THEN null ELSE date(row.effective_to) END,
    p.text_checksum = row.text_checksum,
    p.source_checksum = row.source_checksum,
    p.source_vb_id = row.source_vb_id,
    p.logical_vb_id = row.logical_vb_id,
    p.khoan_id = row.parent_compatibility_id,
    p.van_ban_id = row.source_vb_id,
    p.visibility = coalesce(p.visibility, row.visibility),
    p.recorded_at = coalesce(p.recorded_at, datetime(row.recorded_at)),
    p.review_status = coalesce(p.review_status, row.review_status)
MERGE (parent)-[:CO_DIEM]->(p)
RETURN count(p) AS written_count
""",
}


def _preflight_query(level: str) -> str:
    meta = _LEVEL_META[level]
    return f"""
/* legal_v2_preflight_{meta['marker']} */
UNWIND $rows AS row
OPTIONAL MATCH (legacy:{meta['label']} {{{meta['legacy_key']}: row.compatibility_id}})
OPTIONAL MATCH (version:LegalProvision {{provision_id: row.provision_id}})
RETURN row.provision_id AS requested_id,
       row.compatibility_id AS compatibility_id,
       legacy IS NOT NULL AS legacy_found,
       legacy.provision_id AS legacy_provision_id,
       legacy.text_checksum AS legacy_checksum,
       legacy.{meta['legacy_text']} AS legacy_text,
       version IS NOT NULL AS version_found,
       version.provision_id AS version_provision_id,
       version.text_checksum AS version_checksum,
       version.lineage_id AS version_lineage_id,
       version.level AS version_level,
       coalesce(version.effective_from, legacy.effective_from) AS existing_effective_from,
       coalesce(version.effective_to, legacy.effective_to) AS existing_effective_to,
       coalesce(version.source_vb_id, legacy.source_vb_id) AS existing_source_vb_id,
       coalesce(version.source_checksum, legacy.source_checksum) AS existing_source_checksum,
       coalesce(version.version_no, legacy.version_no) AS existing_version_no
"""


def _parse_date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} is required for LegalProvision v2")
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def _article_text(article: str, title: str, body: str) -> str:
    heading = f"Điều {article}."
    return canonicalize_legal_text(" ".join(part for part in (heading, title, body) if part))


def prepare_legal_provision_rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate one parsed document and flatten it into transaction-ready immutable rows."""
    source_vb_id = str(doc.get("vb_id") or "").strip()
    logical_vb_id = str(
        doc.get("logical_vb_id") or doc.get("so_hieu") or source_vb_id
    ).strip()
    if not source_vb_id or not logical_vb_id:
        raise ValueError("vb_id and logical_vb_id are required")

    document_effective_from = _parse_date(
        doc.get("effective_from") or doc.get("ngay_hieu_luc") or doc.get("ngay_ban_hanh"),
        "effective_from",
    )
    document_effective_to_raw = doc.get("effective_to")
    document_effective_to = (
        _parse_date(document_effective_to_raw, "effective_to")
        if document_effective_to_raw
        else None
    )
    source_checksum = doc.get("source_checksum") or None
    visibility = str(doc.get("visibility") or "public")
    default_version_no = int(doc.get("version_no") or 1)
    review_status = doc.get("review_status") or "approved"

    rows: list[dict[str, Any]] = []
    provision_by_lineage: dict[str, str] = {}
    compatibility_by_lineage: dict[str, str] = {}
    seen_provision_ids: set[str] = set()
    seen_compatibility_ids: set[str] = set()

    def add_row(
        *,
        node: dict[str, Any],
        level: ProvisionLevel,
        compatibility_id: str,
        article: str,
        text: str,
        compatibility_text: str,
        clause: str | None = None,
        point: str | None = None,
        title: str = "",
    ) -> dict[str, Any]:
        if not compatibility_id:
            raise ValueError(f"missing compatibility ID for {level.value}")
        version = build_provision_version(
            logical_vb_id=logical_vb_id,
            source_vb_id=source_vb_id,
            source_checksum=source_checksum,
            level=level,
            article=article,
            clause=clause,
            point=point,
            text=text,
            effective_from=_parse_date(
                node.get("effective_from") or document_effective_from,
                f"{level.value}.effective_from",
            ),
            effective_to=(
                _parse_date(node.get("effective_to"), f"{level.value}.effective_to")
                if node.get("effective_to")
                else document_effective_to
            ),
            version_no=int(node.get("version_no") or default_version_no),
            visibility=visibility,
            review_status=review_status,
        )
        if version.provision_id in seen_provision_ids:
            raise ValueError(f"duplicate provision_id in parsed tree: {version.provision_id}")
        if compatibility_id in seen_compatibility_ids:
            raise ValueError(f"duplicate compatibility ID in parsed tree: {compatibility_id}")
        seen_provision_ids.add(version.provision_id)
        seen_compatibility_ids.add(compatibility_id)

        row = version.model_dump(mode="json")
        row.update(
            {
                "compatibility_id": compatibility_id,
                "compatibility_text": canonicalize_legal_text(compatibility_text),
                "title": title,
                "parent_provision_id": (
                    provision_by_lineage.get(version.parent_lineage_id)
                    if version.parent_lineage_id
                    else None
                ),
                "parent_compatibility_id": (
                    compatibility_by_lineage.get(version.parent_lineage_id)
                    if version.parent_lineage_id
                    else None
                ),
            }
        )
        if version.parent_lineage_id and not row["parent_provision_id"]:
            raise ValueError(
                f"parent provision missing from parsed tree: {version.parent_lineage_id}"
            )
        rows.append(row)
        provision_by_lineage[version.lineage_id] = version.provision_id
        compatibility_by_lineage[version.lineage_id] = compatibility_id
        return row

    for dieu in doc.get("dieu_list") or []:
        article = str(dieu.get("so") or "").strip()
        title = str(dieu.get("tieu_de") or "").strip()
        body = str(dieu.get("noi_dung") or "").strip()
        add_row(
            node=dieu,
            level=ProvisionLevel.DIEU,
            compatibility_id=str(dieu.get("dieu_id") or "").strip(),
            article=article,
            text=_article_text(article, title, body),
            compatibility_text=title,
            title=title,
        )
        for khoan in dieu.get("khoan_list") or []:
            clause = str(khoan.get("so") or "").strip()
            clause_body = str(khoan.get("noi_dung") or "").strip()
            diem_list = khoan.get("diem_list") or []
            if not clause_body and not diem_list:
                raise ValueError(f"leaf Khoản {article}.{clause} has no canonical text")
            clause_text = clause_body or f"Khoản {clause}"
            add_row(
                node=khoan,
                level=ProvisionLevel.KHOAN,
                compatibility_id=str(khoan.get("khoan_id") or "").strip(),
                article=article,
                clause=clause,
                text=clause_text,
                compatibility_text=clause_body,
            )
            for diem in diem_list:
                point = str(diem.get("ky_hieu") or "").replace(")", "").strip().lower()
                point_body = str(diem.get("noi_dung") or "").strip()
                if not point_body:
                    raise ValueError(f"Điểm {article}.{clause}.{point} has no canonical text")
                add_row(
                    node=diem,
                    level=ProvisionLevel.DIEM,
                    compatibility_id=str(diem.get("diem_id") or "").strip(),
                    article=article,
                    clause=clause,
                    point=point,
                    text=point_body,
                    compatibility_text=point_body,
                )

    if not rows:
        raise ValueError("parsed document contains no legal provisions")
    return rows


async def _consume(result: Any) -> None:
    consume = getattr(result, "consume", None)
    if consume is not None:
        await consume()


async def _written_count(result: Any) -> int:
    record = await result.single()
    if not record:
        return 0
    return int(record["written_count"] or 0)


def _record_data(record: Any) -> dict[str, Any]:
    data = getattr(record, "data", None)
    return data() if callable(data) else dict(record)


def _temporal_text(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())[:10]
    return str(value)[:10]


class ImmutableLegalProvisionWriter:
    """Atomic, idempotent writer for the additive LegalProvision v2 schema."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def write_document(
        self,
        doc: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        vb_id = str(doc.get("vb_id") or "").strip() or None
        try:
            rows = prepare_legal_provision_rows(doc)
        except (TypeError, ValueError) as exc:
            return LegalWriteReport(
                status=LegalWriteStatus.INVALID,
                vb_id=vb_id,
                dry_run=dry_run,
                reason=str(exc),
            ).as_dict()

        if not self.driver or not hasattr(self.driver, "session"):
            return LegalWriteReport(
                status=LegalWriteStatus.UNAVAILABLE,
                vb_id=vb_id,
                dry_run=dry_run,
                reason="Neo4j driver is unavailable",
            ).as_dict()

        async with self.driver.session() as session:
            execute_write = getattr(session, "execute_write", None)
            if execute_write is None:
                return LegalWriteReport(
                    status=LegalWriteStatus.UNAVAILABLE,
                    vb_id=vb_id,
                    dry_run=dry_run,
                    reason="Neo4j session does not support managed write transactions",
                ).as_dict()
            report = await execute_write(self._write_transaction, doc, rows, dry_run)
        return report.as_dict()

    @staticmethod
    async def _write_transaction(
        tx: Any,
        doc: dict[str, Any],
        rows: list[dict[str, Any]],
        dry_run: bool,
    ) -> LegalWriteReport:
        by_level: dict[str, list[dict[str, Any]]] = {
            level: [row for row in rows if row["level"] == level]
            for level in _LEVEL_NAMES
        }
        incoming = {level: len(by_level[level]) for level in _LEVEL_NAMES}
        created = {level: 0 for level in _LEVEL_NAMES}
        upgraded = {level: 0 for level in _LEVEL_NAMES}
        idempotent = {level: 0 for level in _LEVEL_NAMES}
        conflicts: list[LegalWriteConflict] = []

        for level in _LEVEL_NAMES:
            level_rows = by_level[level]
            if not level_rows:
                continue
            incoming_by_id = {row["provision_id"]: row for row in level_rows}
            result = await tx.run(_preflight_query(level), rows=level_rows)
            async for raw_record in result:
                record = _record_data(raw_record)
                row = incoming_by_id[record["requested_id"]]
                legacy_found = bool(record.get("legacy_found"))
                version_found = bool(record.get("version_found"))
                legacy_pid = record.get("legacy_provision_id")
                existing_checksum = record.get("version_checksum") or record.get("legacy_checksum")
                reason: str | None = None

                if version_found and not legacy_found:
                    reason = "provision_id_exists_without_compatibility_node"
                elif version_found and legacy_found and not legacy_pid:
                    reason = "provision_id_and_compatibility_id_resolve_to_different_nodes"
                elif legacy_pid and legacy_pid != row["provision_id"]:
                    reason = "compatibility_id_already_bound_to_another_version"
                elif version_found and record.get("version_checksum") != row["text_checksum"]:
                    reason = "same_provision_id_has_different_checksum"
                elif version_found and record.get("version_lineage_id") != row["lineage_id"]:
                    reason = "same_provision_id_has_different_lineage"
                elif version_found and record.get("version_level") != level:
                    reason = "same_provision_id_has_different_level"
                elif (version_found or legacy_pid) and _temporal_text(
                    record.get("existing_effective_from")
                ) != row["effective_from"]:
                    reason = "immutable_node_effective_from_mismatch"
                elif (version_found or legacy_pid) and _temporal_text(
                    record.get("existing_effective_to")
                ) != row["effective_to"]:
                    reason = "immutable_node_effective_to_mismatch"
                elif (version_found or legacy_pid) and record.get(
                    "existing_source_vb_id"
                ) != row["source_vb_id"]:
                    reason = "immutable_node_source_document_mismatch"
                elif (version_found or legacy_pid) and record.get(
                    "existing_source_checksum"
                ) != row["source_checksum"]:
                    reason = "immutable_node_source_checksum_mismatch"
                elif (version_found or legacy_pid) and int(
                    record.get("existing_version_no") or 0
                ) != int(row["version_no"]):
                    reason = "immutable_node_version_number_mismatch"
                elif legacy_pid and record.get("legacy_checksum") != row["text_checksum"]:
                    reason = "immutable_node_checksum_mismatch"
                elif legacy_found and not legacy_pid:
                    existing_text = canonicalize_legal_text(record.get("legacy_text") or "")
                    if existing_text != row["compatibility_text"]:
                        reason = "legacy_node_text_differs_from_incoming_text"
                    else:
                        upgraded[level] += 1
                elif legacy_pid:
                    idempotent[level] += 1
                else:
                    created[level] += 1

                if reason:
                    conflicts.append(
                        LegalWriteConflict(
                            provision_id=row["provision_id"],
                            compatibility_id=row["compatibility_id"],
                            level=level,
                            reason=reason,
                            existing_checksum=existing_checksum,
                            incoming_checksum=row["text_checksum"],
                        )
                    )

        counts = LegalWriteCounts(
            incoming=incoming,
            created=created,
            upgraded=upgraded,
            idempotent=idempotent,
        )
        vb_id = str(doc.get("vb_id") or "").strip() or None
        if conflicts:
            return LegalWriteReport(
                status=LegalWriteStatus.CONFLICT,
                vb_id=vb_id,
                dry_run=dry_run,
                counts=counts,
                conflicts=conflicts,
                reason="immutable write rejected before mutation",
            )
        if dry_run:
            return LegalWriteReport(
                status=LegalWriteStatus.DRY_RUN,
                vb_id=vb_id,
                dry_run=True,
                counts=counts,
            )

        document_params = {
            "vb_id": vb_id,
            "so_hieu": doc.get("so_hieu"),
            "ten": doc.get("ten"),
            "loai": doc.get("loai"),
            "ngay_ban_hanh": doc.get("ngay_ban_hanh"),
            "ngay_hieu_luc": doc.get("ngay_hieu_luc"),
            "trang_thai": doc.get("trang_thai", "hieu_luc"),
            "visibility": doc.get("visibility", "public"),
            "co_quan_ban_hanh": doc.get("co_quan_ban_hanh"),
            "source_filename": doc.get("source_filename"),
            "source_checksum": doc.get("source_checksum"),
        }
        await _consume(await tx.run(_DOCUMENT_QUERY, **document_params))
        for level in _LEVEL_NAMES:
            if by_level[level]:
                result = await tx.run(
                    _WRITE_QUERIES[level],
                    vb_id=vb_id,
                    rows=by_level[level],
                )
                written_count = await _written_count(result)
                if written_count != len(by_level[level]):
                    raise RuntimeError(
                        f"concurrent immutable write conflict at {level}: "
                        f"expected {len(by_level[level])}, wrote {written_count}"
                    )

        status = (
            LegalWriteStatus.WRITTEN
            if counts.total_changed
            else LegalWriteStatus.IDEMPOTENT
        )
        return LegalWriteReport(
            status=status,
            written=True,
            vb_id=vb_id,
            counts=counts,
        )

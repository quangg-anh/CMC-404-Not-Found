"""Shared legal-ingest orchestration used by BOTH the synchronous API path
(`LegalDiffFacade.ingest_document`) and the async Arq worker (`workers.legal_jobs.legal_ingest`).

Flow: raw text/URL -> LegalParser (Điều/Khoản/Điểm) -> canonical IDs -> Neo4j upsert.
Keeping it in one place guarantees the sync and async paths stay identical.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.adapters.neo4j_legal import Neo4jLegalRepository
from app.pipelines.legal.parser import LegalParser
from app.pipelines.legal.extract_text import extract_text
from app.pipelines.legal.normalize import normalize_so_hieu, generate_van_ban_id, generate_khoan_id
from app.pipelines.legal.extractor import LegalExtractor

logger = logging.getLogger(__name__)

# Deterministic namespace so re-ingesting the same Khoản overwrites its vector (idempotent).
_KHOAN_POINT_NAMESPACE = uuid.UUID("6f1a0b2c-3d4e-5f60-8a90-b1c2d3e4f501")


async def _index_khoan_vectors(
    qdrant: Any,
    embedder: Any,
    *,
    vb_id: str,
    so_hieu_norm: str,
    visibility: str,
    dieu_list: list[dict[str, Any]],
) -> int:
    """Embed each Khoản's text and upsert into the Qdrant `khoan` collection.

    This is what makes ingested documents retrievable by the RAG QA engine. Best-effort:
    failures (no embedder model, Qdrant down) are logged and return 0 without failing ingest.
    """
    if not (qdrant and embedder):
        return 0
    entries: list[tuple[str, str, str]] = []  # (khoan_id, noi_dung, dieu_so)
    for dieu in dieu_list:
        for khoan in dieu.get("khoan_list", []):
            text = (khoan.get("noi_dung") or "").strip()
            if text:
                entries.append((khoan["khoan_id"], text, dieu.get("so", "")))
    if not entries:
        return 0
    try:
        vectors = await embedder.embed_texts([e[1] for e in entries])
        points = []
        for (khoan_id, text, dieu_so), vector in zip(entries, vectors):
            points.append(
                {
                    "id": str(uuid.uuid5(_KHOAN_POINT_NAMESPACE, khoan_id)),
                    "vector": vector,
                    "payload": {
                        "khoan_id": khoan_id,
                        "van_ban_id": vb_id,
                        "dieu": dieu_so,
                        "noi_dung": text,
                        "text_preview": text[:200],
                        "visibility": visibility,
                        "so_hieu": so_hieu_norm,
                    },
                }
            )
        await qdrant.upsert("khoan", points)
        return len(points)
    except Exception as exc:  # noqa: BLE001 - indexing is best-effort
        logger.warning("legal_ingest: Qdrant khoan indexing skipped: %s", exc)
        return 0


async def reindex_khoan_from_neo4j(
    driver: Any,
    qdrant: Any,
    embedder: Any,
    van_ban_id: str | None = None,
    batch_size: int = 64,
) -> dict[str, Any]:
    """Backfill/repair Qdrant from Neo4j: embed every Khoản and upsert its vector.

    This makes ALL knowledge that lives in Neo4j retrievable by the RAG QA engine, regardless of
    how it got there (seed scripts, older ingests before vector indexing existed, etc). Idempotent:
    point ids are uuid5(khoan_id), so re-running overwrites rather than duplicates.

    Pass ``van_ban_id`` to reindex a single document, or leave None to reindex everything.
    Returns {status, total, indexed, van_ban_id}.
    """
    if not (driver and hasattr(driver, "session")):
        return {"status": "error", "message": "neo4j_unavailable", "total": 0, "indexed": 0}
    if not (qdrant and embedder):
        return {"status": "error", "message": "qdrant_or_embedder_unavailable", "total": 0, "indexed": 0}

    where = "WHERE v.vb_id = $vb_id" if van_ban_id else ""
    query = f"""
    MATCH (v:VanBanPhapLuat)-[:CO_DIEU]->(d:Dieu)-[:CO_KHOAN]->(k:Khoan)
    {where}
    RETURN k.khoan_id AS khoan_id, k.noi_dung AS noi_dung, k.van_ban_id AS van_ban_id,
           d.so AS dieu_so, coalesce(k.visibility, v.visibility, 'public') AS visibility,
           v.so_hieu AS so_hieu
    """
    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        res = await session.run(query, vb_id=van_ban_id) if van_ban_id else await session.run(query)
        async for record in res:
            rows.append(dict(record))

    entries = [r for r in rows if (r.get("noi_dung") or "").strip()]
    total = len(rows)
    indexed = 0
    for start in range(0, len(entries), batch_size):
        batch = entries[start : start + batch_size]
        try:
            vectors = await embedder.embed_texts([r["noi_dung"].strip() for r in batch])
        except Exception as exc:  # noqa: BLE001
            logger.warning("reindex: embedding batch failed: %s", exc)
            continue
        points = []
        for r, vector in zip(batch, vectors):
            text = r["noi_dung"].strip()
            points.append(
                {
                    "id": str(uuid.uuid5(_KHOAN_POINT_NAMESPACE, r["khoan_id"])),
                    "vector": vector,
                    "payload": {
                        "khoan_id": r["khoan_id"],
                        "van_ban_id": r.get("van_ban_id"),
                        "dieu": r.get("dieu_so", ""),
                        "noi_dung": text,
                        "text_preview": text[:200],
                        "visibility": r.get("visibility", "public"),
                        "so_hieu": r.get("so_hieu", ""),
                    },
                }
            )
        try:
            await qdrant.upsert("khoan", points)
            indexed += len(points)
        except Exception as exc:  # noqa: BLE001
            logger.warning("reindex: qdrant upsert failed: %s", exc)

    return {
        "status": "success",
        "van_ban_id": van_ban_id,
        "total": total,
        "indexed": indexed,
        "message": f"Đã reindex {indexed}/{total} Khoản từ Neo4j vào Qdrant.",
    }


async def _resolve_text(url_or_content: str | None) -> str:
    """Return raw legal text: fetch it if a URL was given, else treat the value as the text."""
    if not url_or_content:
        return ""
    value = url_or_content.strip()
    if value.lower().startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(value)
                resp.raise_for_status()
                return resp.text
        except Exception as exc:  # noqa: BLE001 - network failures degrade to "no content"
            logger.warning("legal_ingest: failed to fetch URL %s: %s", value, exc)
            return ""
    return value


async def _resolve_files_text(pool: Any, minio: Any, file_ids: list[str]) -> str:
    """Read uploaded files from MinIO (by their van_ban_files rows) and extract their text.

    This is the bridge that turns a file sitting in object storage into knowledge the AI can
    learn: bytes -> extract_text() -> plain text -> LegalParser downstream.
    """
    if not (pool and minio and file_ids and hasattr(pool, "acquire")):
        return ""
    ids: list[uuid.UUID] = []
    for fid in file_ids:
        try:
            ids.append(uuid.UUID(str(fid)))
        except (ValueError, TypeError):
            continue
    if not ids:
        return ""

    try:
        from fastapi.concurrency import run_in_threadpool

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT filename, mime, storage_key FROM van_ban_files WHERE file_id = ANY($1::uuid[])",
                ids,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("legal_ingest: failed to load van_ban_files rows: %s", exc)
        return ""

    parts: list[str] = []
    for row in rows:
        try:
            data = await run_in_threadpool(minio.get_bytes, row["storage_key"])
            text = extract_text(data, row["filename"], row["mime"] or "")
            if text.strip():
                parts.append(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("legal_ingest: failed to read/extract %s: %s", row["storage_key"], exc)
    return "\n\n".join(parts)


def _build_tree(so_hieu_norm: str, parsed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach canonical dieu_id/khoan_id to the parser tree for Neo4j MERGE."""
    dieu_list: list[dict[str, Any]] = []
    for dieu in parsed:
        dieu_so = dieu.get("so", "")
        dieu_id = f"{so_hieu_norm}::D{dieu_so}"
        khoan_list = []
        for khoan in dieu.get("khoan_list", []):
            khoan_so = khoan.get("so", "")
            khoan_list.append(
                {
                    "khoan_id": generate_khoan_id(so_hieu_norm, dieu_so, khoan_so),
                    "so": str(khoan_so),
                    "noi_dung": khoan.get("noi_dung", "").strip(),
                }
            )
        dieu_list.append(
            {
                "dieu_id": dieu_id,
                "so": str(dieu_so),
                "tieu_de": dieu.get("tieu_de", "").strip(),
                "khoan_list": khoan_list,
            }
        )
    return dieu_list


async def _run_ner(
    llm_router: Any,
    dieu_list: list[dict[str, Any]],
    vb_id: str,
) -> int:
    """Run NER on every Khoản in dieu_list; returns the number of Khoản successfully extracted.

    Best-effort: exceptions per-Khoản are caught so one bad Khoản never fails the whole batch.
    """
    if llm_router is None:
        return 0
    extractor = LegalExtractor(llm_router=llm_router)
    extracted = 0
    for dieu in dieu_list:
        for khoan in dieu.get("khoan_list", []):
            text = (khoan.get("noi_dung") or "").strip()
            if not text:
                continue
            try:
                result = await extractor.extract_entities_from_khoan(khoan["khoan_id"], text)
                if not result.get("_skip_reason"):
                    extracted += 1
                    logger.debug(
                        "legal_ingest: NER done for %s — chu_the=%d nghia_vu=%d",
                        khoan["khoan_id"],
                        len(result.get("chu_the", [])),
                        len(result.get("nghia_vu", [])),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("legal_ingest: NER failed for khoan %s: %s", khoan.get("khoan_id"), exc)
    return extracted


async def run_legal_ingest(
    driver: Any,
    payload: dict[str, Any],
    qdrant: Any = None,
    embedder: Any = None,
    llm_router: Any = None,
    pool: Any = None,
    minio: Any = None,
) -> dict[str, Any]:
    """Parse the document text, upsert its Điều/Khoản into Neo4j, index Khoản into Qdrant, and run NER.

    Text is resolved in priority order: pasted content/URL first, then any uploaded files
    (``file_ids``) read back from MinIO and text-extracted.

    Returns a status dict:
    {status, vb_id, dieu_count, khoan_count, indexed_count, ner_count, needs_review, message}.
    - status="success" when at least one Điều was written,
    - status="needs_review" when text was present but no structure could be parsed,
    - status="queued" when no content was supplied (awaiting file upload / async fetch).
    """
    so_hieu = payload.get("so_hieu", "")
    so_hieu_norm = normalize_so_hieu(so_hieu) if so_hieu else ""
    ngay_ban_hanh = payload.get("ngay_ban_hanh", "") or ""
    vb_id = generate_van_ban_id(so_hieu_norm, ngay_ban_hanh)

    text = await _resolve_text(payload.get("url_or_content"))
    source = "text/URL"
    if not text.strip():
        file_ids = payload.get("file_ids") or []
        text = await _resolve_files_text(pool, minio, file_ids)
        source = "file"
    if not text.strip():
        return {
            "status": "queued",
            "vb_id": vb_id,
            "dieu_count": 0,
            "khoan_count": 0,
            "indexed_count": 0,
            "needs_review": False,
            "message": "Chưa có nội dung để bóc tách (không có text/URL và không đọc được file đính kèm).",
        }

    parser = LegalParser()
    parsed_tree, needs_review = parser.parse_text(text)
    dieu_list = _build_tree(so_hieu_norm, parsed_tree)

    doc = {
        "vb_id": vb_id,
        "so_hieu": so_hieu_norm,
        "ten": payload.get("ten"),
        "loai": payload.get("loai"),
        "ngay_ban_hanh": ngay_ban_hanh or None,
        "ngay_hieu_luc": payload.get("ngay_hieu_luc") or None,
        "trang_thai": payload.get("trang_thai", "hieu_luc"),
        "visibility": payload.get("visibility", "public"),
        "co_quan_ban_hanh": payload.get("co_quan_ban_hanh"),
        "dieu_list": dieu_list,
    }

    if not dieu_list:
        hint = (
            "Đọc được text từ file nhưng không tách được Điều nào (layout PDF/scan lỗi hoặc cần LLM fallback)."
            if source == "file"
            else "Không bóc tách được Điều nào (layout lỗi hoặc cần LLM fallback)."
        )
        return {
            "status": "needs_review",
            "vb_id": vb_id,
            "dieu_count": 0,
            "khoan_count": 0,
            "indexed_count": 0,
            "needs_review": True,
            "message": hint,
        }

    write_res = await Neo4jLegalRepository(driver).upsert_van_ban(doc)
    khoan_count = write_res.get("khoan_count", 0)

    # Embed + index Khoản into Qdrant so the RAG QA engine can retrieve this new knowledge.
    indexed_count = await _index_khoan_vectors(
        qdrant,
        embedder,
        vb_id=vb_id,
        so_hieu_norm=so_hieu_norm,
        visibility=doc["visibility"],
        dieu_list=dieu_list,
    )

    # Run NER on every Khoản to extract legal entities (best-effort, never blocks).
    ner_count = await _run_ner(llm_router, dieu_list, vb_id)

    index_note = (
        f" · đã index {indexed_count} Khoản cho AI truy hồi"
        if indexed_count
        else " · (chưa index vector — AI chưa truy hồi được)"
    )
    ner_note = f" · NER {ner_count}/{khoan_count} Khoản" if ner_count else ""
    return {
        "status": "success",
        "vb_id": vb_id,
        "dieu_count": len(dieu_list),
        "khoan_count": khoan_count,
        "indexed_count": indexed_count,
        "ner_count": ner_count,
        "needs_review": needs_review,
        "message": f"Đã số hóa {len(dieu_list)} Điều / {khoan_count} Khoản vào đồ thị{index_note}{ner_note}.",
    }

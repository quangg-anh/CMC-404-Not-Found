"""Shared legal-ingest orchestration used by BOTH the synchronous API path
(`LegalDiffFacade.ingest_document`) and the async Arq worker (`workers.legal_jobs.legal_ingest`).

Flow: raw text/URL -> LegalParser (Điều/Khoản/Điểm) -> canonical IDs -> Neo4j upsert.
Keeping it in one place guarantees the sync and async paths stay identical.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from typing import Any

import httpx

from app.adapters.neo4j_legal import Neo4jLegalRepository
from app.config import BE2Config, get_config
from app.domain.legal_provision import build_lineage_id, legal_text_checksum
from app.pipelines.legal.parser import LegalParser
from app.pipelines.legal.extract_text import extract_text
from app.pipelines.legal.normalize import (
    generate_diem_id,
    generate_dieu_id,
    generate_khoan_id,
    generate_van_ban_id,
    normalize_so_hieu,
)
from app.pipelines.legal.extractor import LegalExtractor
from app.pipelines.legal.provision_index import index_document_legal_provisions

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
        details = getattr(exc, "details", None)
        if details:
            logger.warning(
                "legal_ingest: Qdrant khoan indexing skipped: %s | details=%s",
                exc,
                details,
            )
        else:
            logger.warning("legal_ingest: Qdrant khoan indexing skipped: %s", exc)
        return 0


async def reindex_khoan_from_neo4j(
    driver: Any,
    qdrant: Any,
    embedder: Any,
    van_ban_id: str | None = None,
    batch_size: int = 8,
    log_every: int | None = None,
    concurrency: int | None = None,
    skip_existing: bool = True,
) -> dict[str, Any]:
    """Backfill/repair Qdrant from Neo4j: embed every Khoản and upsert its vector.

    This makes ALL knowledge that lives in Neo4j retrievable by the RAG QA engine, regardless of
    how it got there (seed scripts, older ingests before vector indexing existed, etc). Idempotent:
    point ids are uuid5(khoan_id), so re-running overwrites rather than duplicates.

    Pass ``van_ban_id`` to reindex a single document, or leave None to reindex everything.
    ``skip_existing`` (default True): chỉ embed Khoản chưa có trong Qdrant (resume).
    ``log_every`` / env ``REINDEX_LOG_EVERY`` (default 10) controls progress spam.
    ``concurrency`` / env ``REINDEX_CONCURRENCY`` (default 4) = parallel embed+upsert batches.
    Returns {status, total, indexed, van_ban_id}.
    """
    if not (driver and hasattr(driver, "session")):
        return {"status": "error", "message": "neo4j_unavailable", "total": 0, "indexed": 0}
    if not (qdrant and embedder):
        return {"status": "error", "message": "qdrant_or_embedder_unavailable", "total": 0, "indexed": 0}

    if log_every is None:
        try:
            log_every = max(1, int(os.getenv("REINDEX_LOG_EVERY", "10")))
        except ValueError:
            log_every = 10
    if concurrency is None:
        try:
            concurrency = max(1, int(os.getenv("REINDEX_CONCURRENCY", "4")))
        except ValueError:
            concurrency = 4
    concurrency = max(1, min(int(concurrency), 32))

    where = "WHERE v.vb_id = $vb_id" if van_ban_id else ""
    query = f"""
    MATCH (v:VanBanPhapLuat)-[:CO_DIEU]->(d:Dieu)-[:CO_KHOAN]->(k:Khoan)
    {where}
    RETURN k.khoan_id AS khoan_id, k.noi_dung AS noi_dung, k.van_ban_id AS van_ban_id,
           d.so AS dieu_so, coalesce(k.visibility, v.visibility, 'public') AS visibility,
           v.so_hieu AS so_hieu
    """
    print("reindex: dang tai danh sach Khoan tu Neo4j...", flush=True)
    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        res = await session.run(query, vb_id=van_ban_id) if van_ban_id else await session.run(query)
        async for record in res:
            rows.append(dict(record))
            if len(rows) % 5000 == 0:
                print(f"reindex: da doc {len(rows)} rows tu Neo4j...", flush=True)

    entries = [r for r in rows if (r.get("noi_dung") or "").strip() and r.get("khoan_id")]
    total = len(rows)
    usable = len(entries)
    skipped_existing = 0
    if skip_existing and hasattr(qdrant, "list_payload_values"):
        print("reindex: dang quet Qdrant de bo qua Khoan da index...", flush=True)
        existing = await qdrant.list_payload_values("khoan", "khoan_id")
        before = len(entries)
        entries = [r for r in entries if str(r["khoan_id"]) not in existing]
        skipped_existing = before - len(entries)
        print(
            f"reindex: Qdrant da co {len(existing)} khoan_id — skip {skipped_existing}, "
            f"con lai {len(entries)} can embed",
            flush=True,
        )
    elif skip_existing:
        print("reindex: WARN skip_existing bat nhung Qdrant client khong co list_payload_values", flush=True)

    todo = len(entries)
    print(
        f"reindex: Neo4j xong — total={total} usable={usable} todo={todo} "
        f"skip_existing={skipped_existing} batch_size={batch_size} "
        f"concurrency={concurrency} log_every={log_every}",
        flush=True,
    )
    if todo == 0:
        msg = f"Khong con Khoan nao can embed (skip_existing={skipped_existing}/{usable})."
        print(f"reindex: DONE — {msg}", flush=True)
        return {
            "status": "success",
            "van_ban_id": van_ban_id,
            "total": total,
            "usable": usable,
            "todo": 0,
            "skipped_existing": skipped_existing,
            "indexed": 0,
            "message": msg,
        }

    indexed = 0
    failed_batches = 0
    last_error: str | None = None
    fatal_error: str | None = None
    t0 = time.perf_counter()
    last_log_at = 0
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(concurrency)

    def _progress_unlocked(force: bool = False, last_id: str = "") -> None:
        nonlocal last_log_at
        if not force and indexed - last_log_at < log_every and indexed < todo:
            return
        last_log_at = indexed
        elapsed = max(time.perf_counter() - t0, 1e-6)
        rate = indexed / elapsed
        pct = (100.0 * indexed / todo) if todo else 100.0
        remain = max(todo - indexed, 0)
        eta_s = int(remain / rate) if rate > 0 else 0
        eta_m, eta_sec = divmod(eta_s, 60)
        eta_h, eta_m = divmod(eta_m, 60)
        eta = f"{eta_h}h{eta_m:02d}m" if eta_h else f"{eta_m}m{eta_sec:02d}s"
        line = (
            f"reindex: {indexed}/{todo} ({pct:5.1f}%) | "
            f"{rate:.1f} khoan/s | ETA {eta} | fail_batches={failed_batches} | c={concurrency}"
            f" | skipped_existing={skipped_existing}"
        )
        if last_id:
            line += f" | last={last_id}"
        print(line, flush=True)
        logger.info(line)

    def _is_fatal(msg: str) -> bool:
        return any(
            k in msg
            for k in (
                "tokens limit",
                "credit",
                "402",
                "401",
                "no credentials",
                "invalid api key",
                "insufficient",
                "dimension mismatch",
            )
        )

    async def _process_batch(start: int, batch: list[dict[str, Any]]) -> None:
        nonlocal indexed, failed_batches, last_error, fatal_error
        if fatal_error:
            return
        async with sem:
            if fatal_error:
                return
            try:
                vectors = await embedder.embed_texts([r["noi_dung"].strip() for r in batch])
            except Exception as exc:  # noqa: BLE001
                err = f"embed: {exc}"
                details = getattr(exc, "details", None)
                if details:
                    err = f"embed: {exc} | {details}"
                async with lock:
                    failed_batches += 1
                    last_error = err
                    if _is_fatal(str(exc).lower()):
                        fatal_error = err
                print(f"reindex: EMBED FAIL batch@{start}: {err}", flush=True)
                return

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
                async with lock:
                    indexed += len(points)
                    _progress_unlocked(last_id=str(batch[-1].get("khoan_id") or ""))
            except Exception as exc:  # noqa: BLE001
                err = f"qdrant: {exc}"
                async with lock:
                    failed_batches += 1
                    last_error = err
                    if "dimension mismatch" in str(exc).lower():
                        fatal_error = err
                print(f"reindex: QDRANT FAIL batch@{start}: {exc}", flush=True)

    batches = [
        (start, entries[start : start + batch_size])
        for start in range(0, len(entries), batch_size)
    ]
    # Schedule in waves so we don't create 20k Task objects at once.
    wave = max(concurrency * 8, 32)
    for wave_start in range(0, len(batches), wave):
        if fatal_error:
            break
        chunk = batches[wave_start : wave_start + wave]
        await asyncio.gather(*[_process_batch(s, b) for s, b in chunk])

    _progress_unlocked(force=True)
    elapsed = time.perf_counter() - t0
    if fatal_error:
        msg = (
            f"Dung reindex som: {fatal_error}. "
            f"Da index {indexed}/{todo} (skipped_existing={skipped_existing})."
        )
        print(f"reindex: STOP — {msg}", flush=True)
        return {
            "status": "error",
            "van_ban_id": van_ban_id,
            "total": total,
            "usable": usable,
            "todo": todo,
            "skipped_existing": skipped_existing,
            "indexed": indexed,
            "failed_batches": failed_batches,
            "elapsed_s": round(elapsed, 1),
            "last_error": fatal_error,
            "message": msg,
        }

    msg = (
        f"Da reindex {indexed}/{todo} todo "
        f"(usable={usable}, skipped_existing={skipped_existing}, neo4j_rows={total}) "
        f"trong {elapsed:.0f}s — fail_batches={failed_batches} concurrency={concurrency}."
    )
    if indexed < todo and last_error:
        msg += f" (loi gan nhat: {last_error})"
    print(f"reindex: DONE — {msg}", flush=True)
    return {
        "status": "success" if indexed > 0 or skipped_existing > 0 else "error",
        "van_ban_id": van_ban_id,
        "total": total,
        "usable": usable,
        "todo": todo,
        "skipped_existing": skipped_existing,
        "indexed": indexed,
        "failed_batches": failed_batches,
        "elapsed_s": round(elapsed, 1),
        "last_error": last_error,
        "message": msg,
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
    """Attach canonical IDs, lineage and checksums without losing Điểm nodes."""
    dieu_list: list[dict[str, Any]] = []
    for dieu in parsed:
        dieu_so = str(dieu.get("so", "")).strip()
        dieu_id = generate_dieu_id(so_hieu_norm, dieu_so)
        dieu_lineage_id = build_lineage_id(so_hieu_norm, dieu_so)
        dieu_text = str(dieu.get("noi_dung") or "").strip()
        khoan_list: list[dict[str, Any]] = []
        for khoan in dieu.get("khoan_list", []):
            khoan_so = str(khoan.get("so", "")).strip()
            khoan_id = generate_khoan_id(so_hieu_norm, dieu_so, khoan_so)
            khoan_lineage_id = build_lineage_id(so_hieu_norm, dieu_so, khoan_so)
            khoan_text = str(khoan.get("noi_dung") or "").strip()
            diem_list: list[dict[str, Any]] = []
            for diem in khoan.get("diem_list", []):
                ky_hieu = str(diem.get("ky_hieu", "")).replace(")", "").strip().lower()
                diem_text = str(diem.get("noi_dung") or "").strip()
                diem_id = generate_diem_id(khoan_id, ky_hieu)
                diem_list.append(
                    {
                        "diem_id": diem_id,
                        "lineage_id": build_lineage_id(
                            so_hieu_norm,
                            dieu_so,
                            khoan_so,
                            ky_hieu,
                        ),
                        "parent_lineage_id": khoan_lineage_id,
                        "level": "diem",
                        "ky_hieu": ky_hieu,
                        "noi_dung": diem_text,
                        "text_checksum": legal_text_checksum(diem_text),
                    }
                )
            khoan_list.append(
                {
                    "khoan_id": khoan_id,
                    "lineage_id": khoan_lineage_id,
                    "parent_lineage_id": dieu_lineage_id,
                    "level": "khoan",
                    "so": khoan_so,
                    "noi_dung": khoan_text,
                    "text_checksum": legal_text_checksum(khoan_text),
                    "diem_list": diem_list,
                }
            )
        dieu_list.append(
            {
                "dieu_id": dieu_id,
                "lineage_id": dieu_lineage_id,
                "parent_lineage_id": None,
                "level": "dieu",
                "so": dieu_so,
                "tieu_de": str(dieu.get("tieu_de") or "").strip(),
                "noi_dung": dieu_text,
                "text_checksum": legal_text_checksum(dieu_text),
                "khoan_list": khoan_list,
            }
        )
    return dieu_list


async def _run_ner(
    llm_router: Any,
    dieu_list: list[dict[str, Any]],
    vb_id: str,
    driver: Any = None,
) -> int:
    """Run NER on every Khoản in dieu_list and PERSIST the extracted entities into Neo4j.

    Returns the number of Khoản successfully extracted. Best-effort: exceptions per-Khoản are
    caught so one bad Khoản never fails the whole batch.
    """
    if llm_router is None:
        return 0
    extractor = LegalExtractor(llm_router=llm_router)
    repo = Neo4jLegalRepository(driver) if driver is not None else None
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
                    if repo is not None:
                        await repo.upsert_khoan_entities(khoan["khoan_id"], result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("legal_ingest: NER failed for khoan %s: %s", khoan.get("khoan_id"), exc)
    return extracted


async def run_ner_backfill(
    driver: Any,
    llm_router: Any,
    van_ban_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Run NER on Khoản that haven't been processed yet, and persist entities into Neo4j.

    Decoupled from ingest so digitization stays fast: ingest writes the graph + vectors (searchable
    immediately), then this backfill enriches entities in the background / on demand. Processes up
    to ``limit`` Khoản per call; call repeatedly until ``remaining`` is 0. Idempotent (ner_done flag).
    """
    if not (driver and hasattr(driver, "session")):
        return {"status": "error", "message": "neo4j_unavailable", "processed": 0, "entities": 0, "remaining": 0}
    if llm_router is None:
        return {"status": "error", "message": "llm_router_unavailable", "processed": 0, "entities": 0, "remaining": 0}

    repo = Neo4jLegalRepository(driver)
    extractor = LegalExtractor(llm_router=llm_router)
    pending = await repo.list_khoan_needing_ner(van_ban_id=van_ban_id, limit=limit)
    processed = 0
    entities = 0
    for row in pending:
        kid = row["khoan_id"]
        text = (row.get("noi_dung") or "").strip()
        try:
            result = await extractor.extract_entities_from_khoan(kid, text)
            if not result.get("_skip_reason"):
                entities += await repo.upsert_khoan_entities(kid, result)
            else:
                # Mark as done anyway so we don't retry a Khoản the LLM keeps skipping.
                await repo.upsert_khoan_entities(kid, {})
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("run_ner_backfill: NER failed for khoan %s: %s", kid, exc)

    remaining = await repo.count_khoan_needing_ner(van_ban_id=van_ban_id)
    return {
        "status": "success",
        "van_ban_id": van_ban_id,
        "processed": processed,
        "entities": entities,
        "remaining": remaining,
        "message": f"Đã bóc tách thực thể cho {processed} Khoản ({entities} thực thể). Còn lại {remaining}.",
    }


def _ner_on_ingest_default() -> bool:
    """Whether NER runs inline during ingest. Default OFF: NER is a slow per-Khoản LLM call and is
    now decoupled into run_ner_backfill, so bulk/large ingests stay fast. Set LEGAL_NER_ON_INGEST=1
    to re-enable inline NER for single documents."""
    import os

    return os.getenv("LEGAL_NER_ON_INGEST", "0") == "1"


async def run_legal_ingest(
    driver: Any,
    payload: dict[str, Any],
    qdrant: Any = None,
    embedder: Any = None,
    llm_router: Any = None,
    pool: Any = None,
    minio: Any = None,
    run_ner: bool | None = None,
    config: BE2Config | None = None,
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
    cfg = config or get_config()
    so_hieu = payload.get("so_hieu", "")
    so_hieu_norm = normalize_so_hieu(so_hieu) if so_hieu else ""
    ngay_ban_hanh = payload.get("ngay_ban_hanh", "") or ""
    vb_id = generate_van_ban_id(so_hieu_norm, ngay_ban_hanh)

    text = await _resolve_text(payload.get("url_or_content"))
    source = "text/URL"
    file_ids = payload.get("file_ids") or []
    if not text.strip() and file_ids:
        text = await _resolve_files_text(pool, minio, file_ids)
        source = "file"
    if not text.strip():
        # A file WAS uploaded but no text could be pulled out of it → almost always a scanned/
        # image-only PDF (no text layer). Surface this as needs_review with an actionable hint
        # instead of a silent "queued" that looks like the job is stuck forever.
        if file_ids:
            return {
                "status": "needs_review",
                "vb_id": vb_id,
                "dieu_count": 0,
                "khoan_count": 0,
                "indexed_count": 0,
                "needs_review": True,
                "message": (
                    "Không trích được chữ nào từ file — nhiều khả năng đây là PDF scan (ảnh) "
                    "không có lớp text. Hãy bật OCR (cài Tesseract + gói tiếng Việt 'vie') hoặc "
                    "dán trực tiếp nội dung văn bản vào ô nội dung để số hóa."
                ),
            }
        return {
            "status": "queued",
            "vb_id": vb_id,
            "dieu_count": 0,
            "khoan_count": 0,
            "indexed_count": 0,
            "needs_review": False,
            "message": "Chưa có nội dung để bóc tách (không có text/URL và không có file đính kèm).",
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
        "source_filename": payload.get("source_filename"),
        "logical_vb_id": payload.get("logical_vb_id") or so_hieu_norm,
        "source_checksum": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "review_status": "needs_review" if needs_review else "approved",
        "version_no": int(payload.get("version_no") or 1),
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

    repo = Neo4jLegalRepository(driver)
    v2_write_report: dict[str, Any] | None = None
    diem_count = sum(
        len(khoan.get("diem_list") or [])
        for dieu in dieu_list
        for khoan in dieu.get("khoan_list") or []
    )
    if cfg.legal_provision_v2_write:
        # Write legacy and immutable properties atomically on the same nodes. Replacing the
        # mutable v1 writer here prevents a rejected v2 conflict from being overwritten by v1.
        v2_write_report = await repo.upsert_van_ban_v2(doc)
        v2_status = v2_write_report.get("status")
        incoming = (v2_write_report.get("counts") or {}).get("incoming") or {}
        khoan_count = int(incoming.get("khoan", 0))
        diem_count = int(incoming.get("diem", diem_count))
        if v2_status in {"conflict", "invalid"}:
            return {
                "status": "needs_review",
                "vb_id": vb_id,
                "dieu_count": len(dieu_list),
                "khoan_count": khoan_count,
                "diem_count": diem_count,
                "indexed_count": 0,
                "ner_count": 0,
                "needs_review": True,
                "write_mode": "legal_provision_v2",
                "v2_write_report": v2_write_report,
                "message": "LegalProvision v2 từ chối ghi để bảo toàn nội dung bất biến; cần Admin rà soát.",
            }
        if v2_status == "neo4j_unavailable":
            return {
                "status": "error",
                "vb_id": vb_id,
                "dieu_count": len(dieu_list),
                "khoan_count": 0,
                "diem_count": diem_count,
                "indexed_count": 0,
                "ner_count": 0,
                "needs_review": False,
                "write_mode": "legal_provision_v2",
                "v2_write_report": v2_write_report,
                "message": v2_write_report.get("reason") or "Neo4j v2 writer unavailable.",
            }
    else:
        write_res = await repo.upsert_van_ban(doc)
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
    v2_indexed_count = 0
    if cfg.legal_provision_v2_write and (v2_write_report or {}).get("status") in {
        "written",
        "idempotent",
    }:
        try:
            v2_indexed_count = await index_document_legal_provisions(
                qdrant,
                embedder,
                doc,
            )
        except Exception as exc:  # noqa: BLE001 - keep legacy retrieval available
            logger.warning(
                "legal_ingest: Qdrant legal_provision indexing skipped: %s",
                exc,
            )

    # NER is decoupled by default (run via run_ner_backfill) so ingest stays fast. Only run inline
    # when explicitly requested (run_ner=True) or when LEGAL_NER_ON_INGEST=1.
    should_ner = _ner_on_ingest_default() if run_ner is None else run_ner
    ner_count = await _run_ner(llm_router, dieu_list, vb_id, driver=driver) if should_ner else 0

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
        "diem_count": diem_count,
        "indexed_count": indexed_count,
        "v2_indexed_count": v2_indexed_count,
        "ner_count": ner_count,
        "needs_review": needs_review,
        "write_mode": "legal_provision_v2" if cfg.legal_provision_v2_write else "legacy_v1",
        "v2_write_report": v2_write_report,
        "message": f"Đã số hóa {len(dieu_list)} Điều / {khoan_count} Khoản / {diem_count} Điểm vào đồ thị{index_note}{ner_note}.",
    }

from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Any
from datetime import datetime, timezone
from app.pipelines.legal.version_diff import VersionDiff
from app.pipelines.legal.normalize import normalize_so_hieu, generate_van_ban_id
from app.pipelines.legal.pipeline import run_legal_ingest, reindex_khoan_from_neo4j

_JOB_STATUSES = {"queued", "running", "success", "error", "needs_review"}


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert Neo4j driver values (temporal/spatial types) into JSON-safe values.

    Neo4j returns dates as ``neo4j.time.Date``/``DateTime`` etc., which pydantic cannot serialize.
    Anything not natively JSON-serializable is coerced to its string form.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    iso = getattr(obj, "iso_format", None)
    if callable(iso):
        return iso()
    return str(obj)


class LegalDiffFacade:
    """Facade orchestrating BE1 legal pipeline calls, version diffing, and legal document queries from real DB/Graph."""

    def __init__(
        self,
        pool: Any | None = None,
        neo4j_driver: Any | None = None,
        qdrant: Any | None = None,
        embedder: Any | None = None,
        llm_router: Any | None = None,
        minio: Any | None = None,
    ) -> None:
        self.pool = pool
        self.driver = neo4j_driver
        self.qdrant = qdrant
        self.embedder = embedder
        self.llm_router = llm_router
        self.minio = minio
        self.differ = VersionDiff()

    async def store_upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
        so_hieu: str,
        visibility: str = "internal",
    ) -> dict[str, Any]:
        """Store a raw uploaded file into MinIO and mirror its metadata into van_ban_files.

        Returns {file_id, storage_key, filename, checksum, van_ban_id, size_bytes} so the caller
        can pass ``file_id`` into the ingest request. Idempotent per (van_ban_id, checksum).
        """
        from fastapi.concurrency import run_in_threadpool

        if not self.minio:
            raise RuntimeError("MinIO storage unavailable")
        checksum = hashlib.sha256(data).hexdigest()
        so_hieu_norm = normalize_so_hieu(so_hieu) if so_hieu else ""
        vb_id = generate_van_ban_id(so_hieu_norm, "")
        vis = visibility if visibility in {"public", "internal"} else "internal"
        storage_key = self.minio.build_key(checksum, filename)
        await run_in_threadpool(self.minio.put_bytes, storage_key, data, content_type)

        file_id = str(uuid.uuid4())
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO van_ban_files
                            (file_id, van_ban_id, filename, mime, storage_key, checksum, visibility)
                        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::visibility)
                        ON CONFLICT (van_ban_id, checksum)
                            DO UPDATE SET filename = EXCLUDED.filename,
                                          mime = EXCLUDED.mime,
                                          storage_key = EXCLUDED.storage_key
                        RETURNING file_id
                        """,
                        file_id,
                        vb_id,
                        filename,
                        content_type,
                        storage_key,
                        checksum,
                        vis,
                    )
                    if row and row.get("file_id"):
                        file_id = str(row["file_id"])
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Không ghi được metadata file: {exc}") from exc

        return {
            "file_id": file_id,
            "storage_key": storage_key,
            "filename": filename,
            "checksum": checksum,
            "van_ban_id": vb_id,
            "size_bytes": len(data),
        }

    async def ingest_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Ingest a legal document.

        Persists a `jobs` row, then either (A) processes it synchronously — parse text into
        Điều/Khoản and upsert into Neo4j so the document is immediately queryable — or (B) hands
        it off to the real Arq worker when ``LEGAL_INGEST_ASYNC=1`` and Redis is reachable.
        """
        so_hieu = payload.get("so_hieu", "")
        norm_so_hieu = normalize_so_hieu(so_hieu) if so_hieu else ""
        # jobs.id is UUID (default gen_random_uuid()); use a real UUID, not a "job-legal-*" string.
        job_id = str(uuid.uuid4())

        await self._insert_job(job_id, payload)

        # Async path (B): enqueue to the Arq worker if explicitly enabled and reachable.
        if os.getenv("LEGAL_INGEST_ASYNC", "0") == "1":
            if await self._enqueue_arq("legal_ingest", job_id, payload):
                return {
                    "job_id": job_id,
                    "so_hieu": norm_so_hieu,
                    "status": "queued",
                    "message": "Đã đưa vào hàng đợi Arq để worker xử lý bất đồng bộ.",
                }

        # Synchronous path (A): parse + write to Neo4j + index vectors + NER now.
        result = await run_legal_ingest(
            self.driver,
            payload,
            qdrant=self.qdrant,
            embedder=self.embedder,
            llm_router=self.llm_router,
            pool=self.pool,
            minio=self.minio,
        )
        await self._update_job_status(job_id, result["status"], result.get("message"))
        return {
            "job_id": job_id,
            "so_hieu": norm_so_hieu,
            "vb_id": result.get("vb_id"),
            "status": result["status"],
            "dieu_count": result.get("dieu_count", 0),
            "khoan_count": result.get("khoan_count", 0),
            "indexed_count": result.get("indexed_count", 0),
            "ner_count": result.get("ner_count", 0),
            "needs_review": result.get("needs_review", False),
            "message": result.get("message", "Đã xử lý."),
        }

    async def reindex_vectors(self, van_ban_id: str | None = None) -> dict[str, Any]:
        """Backfill Qdrant from Neo4j so ALL digitized Khoản become retrievable by the AI."""
        return await reindex_khoan_from_neo4j(self.driver, self.qdrant, self.embedder, van_ban_id)

    async def _insert_job(self, job_id: str, payload: dict[str, Any]) -> None:
        if not (self.pool and hasattr(self.pool, "acquire")):
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO jobs (id, type, status, payload_json, created_at)
                    VALUES ($1::uuid, 'legal_ingest', 'queued', $2::jsonb, $3)
                    ON CONFLICT DO NOTHING
                    """,
                    job_id,
                    json.dumps(payload),
                    datetime.now(timezone.utc),
                )
        except Exception:
            pass

    async def _update_job_status(self, job_id: str, status: str, message: str | None = None) -> None:
        db_status = status if status in _JOB_STATUSES else "error"
        err = message if db_status in {"error", "needs_review"} else None
        if not (self.pool and hasattr(self.pool, "acquire")):
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE jobs SET status = $1::job_status, error = $2, updated_at = now() WHERE id = $3::uuid",
                    db_status,
                    err,
                    job_id,
                )
        except Exception:
            pass

    async def _enqueue_arq(self, func_name: str, job_id: str, payload: dict[str, Any]) -> bool:
        try:
            from arq import create_pool
            from app.workers.arq_settings import redis_settings

            pool = await create_pool(redis_settings())
            await pool.enqueue_job(func_name, job_id, payload)
            await pool.close()
            return True
        except Exception:
            return False

    async def list_van_ban(self, visibility: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """List legal documents from Neo4j (VanBanPhapLuat node or Postgres van_ban table)."""
        items: list[dict[str, Any]] = []
        if self.driver and hasattr(self.driver, "session"):
            try:
                query = "MATCH (v:VanBanPhapLuat) RETURN v ORDER BY v.ngay_ban_hanh DESC LIMIT 100"
                async with self.driver.session() as session:
                    res = await session.run(query)
                    async for record in res:
                        data = _to_jsonable(dict(record["v"]))
                        if visibility and data.get("visibility") != visibility:
                            continue
                        if status and data.get("trang_thai") != status:
                            continue
                        items.append(data)
            except Exception:
                pass

        if not items and self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch("SELECT * FROM van_ban ORDER BY ngay_ban_hanh DESC LIMIT 100")
                    for r in rows:
                        data = dict(r)
                        if visibility and data.get("visibility") != visibility:
                            continue
                        if status and data.get("trang_thai") != status:
                            continue
                        items.append(data)
            except Exception:
                pass

        return items

    async def get_van_ban_detail(self, van_ban_id: str) -> dict[str, Any] | None:
        """Fetch real legal document node & Khoan hierarchy from Neo4j."""
        if self.driver and hasattr(self.driver, "session"):
            try:
                query = """
                MATCH (v:VanBanPhapLuat)
                WHERE v.vb_id = $id OR v.so_hieu = $id OR id(v) = $id
                OPTIONAL MATCH (v)-[:CO_DIEU|CO_KHOAN*1..2]->(k:Khoan)
                RETURN v, collect(k) AS khoans
                """
                async with self.driver.session() as session:
                    res = await session.run(query, id=van_ban_id)
                    record = await res.single()
                    if record and record["v"]:
                        doc = _to_jsonable(dict(record["v"]))
                        khoans = [_to_jsonable(dict(k)) for k in record["khoans"] if k is not None]
                        doc["tree"] = khoans
                        return doc
            except Exception:
                pass

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT * FROM van_ban WHERE id = $1 OR so_hieu = $1", van_ban_id)
                    if row:
                        doc = dict(row)
                        krows = await conn.fetch("SELECT * FROM khoan WHERE van_ban_id = $1 ORDER BY so_khoan ASC", doc.get("id", van_ban_id))
                        doc["tree"] = [dict(k) for k in krows]
                        return doc
            except Exception:
                pass

        return None

    async def get_khoan_detail(self, khoan_id: str) -> dict[str, Any] | None:
        """Fetch exact Khoan node and related legal entities from Neo4j."""
        if self.driver and hasattr(self.driver, "session"):
            try:
                query = """
                MATCH (k:Khoan)
                WHERE k.khoan_id = $id OR id(k) = $id
                OPTIONAL MATCH (k)-[r:QUY_DINH|AP_DUNG_CHO|THAY_THE]->(e)
                RETURN k, collect({rel: type(r), entity: e}) AS entities
                """
                async with self.driver.session() as session:
                    res = await session.run(query, id=khoan_id)
                    record = await res.single()
                    if record and record["k"]:
                        item = _to_jsonable(dict(record["k"]))
                        item["entities"] = [_to_jsonable(dict(x["entity"])) for x in record["entities"] if x["entity"] is not None]
                        return item
            except Exception:
                pass

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT * FROM khoan WHERE id = $1 OR khoan_id = $1", khoan_id)
                    if row:
                        return dict(row)
            except Exception:
                pass

        return None

    async def compute_diff(self, old_text: str, new_text: str, method: str = "auto") -> dict[str, Any]:
        """Compute structural hunks and similarity diff between two legal segments."""
        hunks = self.differ.diff(old_text, new_text)
        return {
            "hunks": hunks,
            "method": method,
            "old_text": old_text,
            "new_text": new_text,
            "total_hunks": len(hunks),
        }

    async def list_files(self, van_ban_id: str) -> list[dict[str, Any]]:
        """List real files from Postgres files table."""
        items: list[dict[str, Any]] = []
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch("SELECT * FROM files WHERE van_ban_id = $1", van_ban_id)
                    for r in rows:
                        items.append(dict(r))
            except Exception:
                pass
        return items

    async def get_file_detail(self, file_id: str) -> dict[str, Any] | None:
        """Fetch file metadata from Postgres files table."""
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT * FROM files WHERE id = $1 OR file_id = $1", file_id)
                    if row:
                        return dict(row)
            except Exception:
                pass
        return None

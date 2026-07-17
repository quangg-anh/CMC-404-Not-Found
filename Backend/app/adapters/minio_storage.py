"""MinIO (S3-compatible) object storage adapter for raw legal files.

Stores immutable original uploads (PDF/DOCX/TXT) into the ``legal-raw`` bucket and reads them
back for the ingest pipeline. The underlying ``minio`` client is synchronous, so callers should
invoke ``put_bytes``/``get_bytes`` via ``fastapi.concurrency.run_in_threadpool`` to avoid blocking
the event loop.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class MinioStorage:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def ensure_bucket(self) -> None:
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except Exception as exc:  # noqa: BLE001 - bucket may already exist / race
            logger.warning("minio ensure_bucket(%s) failed: %s", self.bucket, exc)

    @staticmethod
    def build_key(checksum: str, filename: str) -> str:
        """Object key layout: {yyyy}/{mm}/{checksum}/{filename} (matches van_ban_files.storage_key)."""
        now = datetime.now(timezone.utc)
        safe_name = (filename or "file").replace("\\", "_").replace("/", "_")
        return f"{now:%Y/%m}/{checksum}/{safe_name}"

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        self.ensure_bucket()
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )
        return key

    def get_bytes(self, key: str) -> bytes:
        resp = self.client.get_object(self.bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()
